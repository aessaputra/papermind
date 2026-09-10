import asyncio
import logging
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.config import settings
from app.schemas import UserPayload

logger = logging.getLogger(__name__)

security = HTTPBearer()

ASYMMETRIC_PREFIXES = ("RS", "ES", "PS")
HMAC_ALGORITHMS = ["HS256", "HS384", "HS512"]


@lru_cache(maxsize=1)
def get_jwks_client() -> PyJWKClient | None:
    jwks_url = getattr(settings, "SUPABASE_JWKS_URL", None)
    if not jwks_url:
        return None
    try:
        return PyJWKClient(jwks_url)
    except Exception as e:
        logger.warning("Failed to initialize JWKS client from %s: %s", jwks_url, e)
        return None


def _is_asymmetric_algorithm(algorithm: str) -> bool:
    return algorithm.startswith(ASYMMETRIC_PREFIXES) or algorithm == "EdDSA"


async def _decode_jwt_token(token: str, secret: str, audience: str) -> dict:
    header = jwt.get_unverified_header(token)
    algorithm = header.get("alg", "HS256")
    kid = header.get("kid")

    jwks_client = get_jwks_client() if kid and _is_asymmetric_algorithm(algorithm) else None

    if jwks_client:
        signing_key = await asyncio.to_thread(jwks_client.get_signing_key_from_jwt, token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=[algorithm],
            audience=audience,
            leeway=60,
        )

    return jwt.decode(
        token,
        secret,
        algorithms=HMAC_ALGORITHMS,
        audience=audience,
        leeway=60,
    )


def _extract_user_payload(payload: dict) -> UserPayload:
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload is missing required 'sub' claim.",
        )

    email = payload.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload is missing required 'email' claim.",
        )

    role = payload.get("role", "authenticated")
    return UserPayload(user_id=user_id, email=email, role=role)


async def verify_supabase_token(token: str, secret: str | None = None) -> UserPayload:
    effective_secret = secret or settings.SUPABASE_JWT_SECRET
    audience = settings.SUPABASE_JWT_AUDIENCE

    try:
        payload = await _decode_jwt_token(token, effective_secret, audience)
        return _extract_user_payload(payload)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired.",
        )
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        logger.warning("JWT verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
        )


CredentialsDep = Annotated[HTTPAuthorizationCredentials, Depends(security)]

async def get_current_user(
    credentials: CredentialsDep,
) -> UserPayload:
    """FastAPI dependency that extracts and verifies the current user from the Bearer token."""
    return await verify_supabase_token(credentials.credentials)


CurrentUserDep = Annotated[UserPayload, Depends(get_current_user)]
