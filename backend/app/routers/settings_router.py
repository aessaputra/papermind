
import hashlib
import ipaddress
import time
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, status

from app.auth import CurrentUserDep
from app.database import execute_query, get_supabase_client
from app.schemas import (
    EmbeddingConfigResponse,
    EmbeddingConfigSaveRequest,
    EnrichmentConfigRequest,
    EnrichmentConfigResponse,
    ProviderConfigCreate,
    ProviderConfigResponse,
    ProviderConfigUpdate,
    VerifyModelsRequest,
    VerifyModelsResponse,
)
from app.services.crypto_service import CryptoService
from app.services.enrichment_job_service import DEFAULT_PRESET, get_preset_cap
from app.services import model_service

router = APIRouter(
    prefix="/api/settings",
    tags=["Settings"],
)


def _format_config_response(record: dict) -> ProviderConfigResponse:
    return ProviderConfigResponse(
        id=str(record["id"]),
        provider=record["provider"],
        display_name=record.get("display_name"),
        base_url=record.get("base_url"),
        model_name=record.get("model_name"),
        is_default=record.get("is_default", False),
    )


@router.get("/providers", response_model=list[ProviderConfigResponse])
async def list_provider_configs(user: CurrentUserDep) -> list[ProviderConfigResponse]:
    supabase = await get_supabase_client()
    response = await execute_query(
        supabase.table("user_provider_configs")
        .select("id, provider, display_name, base_url, model_name, is_default")
        .eq("user_id", user.user_id)
        .order("created_at", desc=True)
    )

    records = response.data if response.data else []
    return [_format_config_response(r) for r in records]


@router.post("/providers", response_model=ProviderConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_provider_config(
    payload: ProviderConfigCreate,
    user: CurrentUserDep,
) -> ProviderConfigResponse:
    supabase = await get_supabase_client()
    crypto = CryptoService()

    if payload.is_default:
        await execute_query(
            supabase.table("user_provider_configs")
            .update({"is_default": False})
            .eq("user_id", user.user_id)
        )

    encrypted_api_key = crypto.encrypt(payload.api_key)

    data = {
        "user_id": user.user_id,
        "provider": payload.provider,
        "display_name": payload.display_name,
        "api_key_enc": encrypted_api_key,
        "base_url": payload.base_url,
        "model_name": payload.model_name,
        "is_default": payload.is_default,
    }

    response = await execute_query(supabase.table("user_provider_configs").insert(data))
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gagal menyimpan konfigurasi provider."
        )

    return _format_config_response(response.data[0])


_VERIFY_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_VERIFY_CACHE_TTL_SECONDS = 300.0
_VERIFY_USER_CALLS: dict[str, list[float]] = {}
VERIFY_MAX_CALLS_PER_MINUTE = 20


def _verify_request_key(user_id: str, payload: "VerifyModelsRequest") -> str:
    raw_key = payload.api_key or ""
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()[:16] if raw_key else "saved"
    return "|".join([user_id, payload.provider, payload.model_type, key_hash, payload.base_url or "", payload.config_id or ""])


def _get_cached_verify(bucket_key: str) -> dict[str, Any] | None:
    hit = _VERIFY_CACHE.get(bucket_key)
    if hit and time.monotonic() - hit[0] < _VERIFY_CACHE_TTL_SECONDS:
        return hit[1]
    return None


def _check_verify_rate_limit(user_id: str) -> None:
    now = time.monotonic()
    if len(_VERIFY_USER_CALLS) > 1024:
        _VERIFY_USER_CALLS.clear()
    calls = [t for t in _VERIFY_USER_CALLS.get(user_id, []) if now - t < 60.0]
    if len(calls) >= VERIFY_MAX_CALLS_PER_MINUTE:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many verification requests. Please wait a minute.",
        )
    _VERIFY_USER_CALLS[user_id] = [*calls, now]


def _validate_public_base_url(base_url: str | None) -> None:
    if not base_url:
        return
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="base_url must use http or https scheme.",
        )
    try:
        ip = ipaddress.ip_address(parsed.hostname or "")
    except ValueError:
        return
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="base_url must not target internal network addresses.",
        )


@router.post("/providers/verify-models", response_model=VerifyModelsResponse)
async def verify_and_list_models(
    payload: VerifyModelsRequest,
    user: CurrentUserDep,
) -> VerifyModelsResponse:
    bucket_key = _verify_request_key(user.user_id, payload)
    cached = _get_cached_verify(bucket_key)
    if cached is not None:
        return VerifyModelsResponse(**cached)
    _validate_public_base_url(payload.base_url)
    _check_verify_rate_limit(user.user_id)
    api_key = payload.api_key
    base_url = payload.base_url

    if not api_key and payload.config_id:
        supabase = await get_supabase_client()
        crypto = CryptoService()
        existing = await execute_query(
            supabase.table("user_provider_configs")
            .select("api_key_enc, base_url")
            .eq("id", payload.config_id)
            .eq("user_id", user.user_id)
        )
        key_from_db = crypto.decrypt(existing.data[0].get("api_key_enc", "")) if existing.data else None
        url_from_db = existing.data[0].get("base_url") if existing.data else None
        if key_from_db:
            api_key = key_from_db
        if not base_url:
            base_url = url_from_db

    res = await model_service.fetch_available_models(
        provider=payload.provider,
        api_key=api_key or "",
        base_url=base_url,
        model_type=payload.model_type,
    )
    if len(_VERIFY_CACHE) > 1024:
        _VERIFY_CACHE.clear()
    _VERIFY_CACHE[bucket_key] = (time.monotonic(), res)
    return VerifyModelsResponse(**res)


@router.put("/providers/{config_id}", response_model=ProviderConfigResponse)
async def update_provider_config(
    config_id: str,
    payload: ProviderConfigUpdate,
    user: CurrentUserDep,
) -> ProviderConfigResponse:
    supabase = await get_supabase_client()
    crypto = CryptoService()

    existing = await execute_query(
        supabase.table("user_provider_configs")
        .select("id, provider, display_name, base_url, model_name, is_default")
        .eq("id", config_id)
        .eq("user_id", user.user_id)
    )

    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Konfigurasi provider tidak ditemukan."
        )

    update_data = payload.model_dump(exclude_unset=True, exclude={"api_key"})
    
    if payload.api_key:
        update_data["api_key_enc"] = crypto.encrypt(payload.api_key)

    if payload.is_default:
        await execute_query(
            supabase.table("user_provider_configs")
            .update({"is_default": False})
            .eq("user_id", user.user_id)
        )

    if not update_data:
        return _format_config_response(existing.data[0])

    response = await execute_query(
        supabase.table("user_provider_configs")
        .update(update_data)
        .eq("id", config_id)
        .eq("user_id", user.user_id)
    )

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gagal memperbarui konfigurasi provider."
        )

    return _format_config_response(response.data[0])


@router.delete("/providers/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider_config(
    config_id: str,
    user: CurrentUserDep,
) -> None:
    supabase = await get_supabase_client()

    existing = await execute_query(
        supabase.table("user_provider_configs")
        .select("id")
        .eq("id", config_id)
        .eq("user_id", user.user_id)
    )

    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Konfigurasi provider tidak ditemukan."
        )

    await execute_query(supabase.table("user_provider_configs").delete().eq("id", config_id).eq("user_id", user.user_id))


def _format_embedding_response(record: dict, is_locked: bool) -> EmbeddingConfigResponse:
    return EmbeddingConfigResponse(
        provider=record["provider"],
        base_url=record.get("base_url"),
        model_name=record["model_name"],
        embedding_dimensions=record.get("embedding_dimensions", 768),
        locked=is_locked,
    )


@router.get("/embedding", response_model=EmbeddingConfigResponse)
async def get_embedding_config(user: CurrentUserDep) -> EmbeddingConfigResponse:
    supabase = await get_supabase_client()
    config_res = await execute_query(
        supabase.table("user_embedding_configs")
        .select("provider, base_url, model_name, embedding_dimensions")
        .eq("user_id", user.user_id)
    )

    if not config_res.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Konfigurasi embedding belum diatur."
        )

    doc_count_res = await execute_query(
        supabase.table("documents")
        .select("id", count="exact")
        .eq("user_id", user.user_id)
    )
    is_locked = (doc_count_res.count or 0) > 0

    return _format_embedding_response(config_res.data[0], is_locked)


@router.post("/embedding", response_model=EmbeddingConfigResponse)
async def save_embedding_config(
    payload: EmbeddingConfigSaveRequest,
    user: CurrentUserDep,
) -> EmbeddingConfigResponse:
    supabase = await get_supabase_client()
    crypto = CryptoService()

    doc_count_res = await execute_query(
        supabase.table("documents")
        .select("id", count="exact")
        .eq("user_id", user.user_id)
    )
    has_documents = (doc_count_res.count or 0) > 0

    existing_res = await execute_query(
        supabase.table("user_embedding_configs")
        .select("provider, base_url, model_name, embedding_dimensions")
        .eq("user_id", user.user_id)
    )

    if has_documents and existing_res.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Model embedding telah terkunci karena Anda memiliki dokumen PDF yang diunggah. Hapus semua dokumen terlebih dahulu untuk mengganti model embedding."
        )

    api_key_enc = None
    if payload.api_key:
        api_key_enc = crypto.encrypt(payload.api_key)
    else:
        provider_res = await execute_query(
            supabase.table("user_provider_configs")
            .select("api_key_enc")
            .eq("user_id", user.user_id)
            .eq("provider", payload.provider)
            .limit(1)
        )
        if provider_res.data:
            api_key_enc = provider_res.data[0]["api_key_enc"]

    if not api_key_enc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"API key untuk provider '{payload.provider}' belum dikonfigurasi. Masukkan API key atau simpan Provider Config terlebih dahulu."
        )

    dimensions = payload.embedding_dimensions
    if dimensions is None:
        raw_key = payload.api_key or (
            crypto.decrypt(api_key_enc) if api_key_enc else ""
        )
        probed = await model_service.fetch_available_models(
            provider=payload.provider,
            api_key=raw_key,
            base_url=payload.base_url,
            model_type="embedding",
        )
        if not probed.get("success"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=probed.get("error") or "Verifikasi embedding gagal. Isi kolom DIMENSI secara manual.",
            )
        # auto: store NULL, dimensions omitted from gateway requests at runtime.

    data = {
        "user_id": user.user_id,
        "provider": payload.provider,
        "api_key_enc": api_key_enc,
        "base_url": payload.base_url,
        "model_name": payload.model_name,
        "embedding_dimensions": dimensions,
    }

    upsert_res = await execute_query(
        supabase.table("user_embedding_configs")
        .upsert(data, on_conflict="user_id")
    )

    if not upsert_res.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gagal menyimpan konfigurasi model embedding."
        )

    return _format_embedding_response(upsert_res.data[0], has_documents)


@router.get("/enrichment", response_model=EnrichmentConfigResponse)
async def get_enrichment_config(user: CurrentUserDep) -> EnrichmentConfigResponse:
    supabase = await get_supabase_client()
    response = await execute_query(
        supabase.table("user_enrichment_configs")
        .select("preset")
        .eq("user_id", user.user_id)
    )
    preset = response.data[0].get("preset", DEFAULT_PRESET) if response.data else DEFAULT_PRESET
    return EnrichmentConfigResponse(
        preset=preset,
        max_enriched_paragraphs=get_preset_cap(preset),
    )


@router.put("/enrichment", response_model=EnrichmentConfigResponse)
async def save_enrichment_config(
    payload: EnrichmentConfigRequest,
    user: CurrentUserDep,
) -> EnrichmentConfigResponse:
    supabase = await get_supabase_client()
    response = await execute_query(
        supabase.table("user_enrichment_configs")
        .upsert({"user_id": user.user_id, "preset": payload.preset}, on_conflict="user_id")
    )

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gagal menyimpan konfigurasi enrichment."
        )

    preset = response.data[0].get("preset", payload.preset)
    return EnrichmentConfigResponse(
        preset=preset,
        max_enriched_paragraphs=get_preset_cap(preset),
    )

