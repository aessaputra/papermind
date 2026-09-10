"""
Database Connection Module

Provides cached access to the async Supabase admin client instance.
The admin client uses the service role key and bypasses RLS — use only for
server-side operations that intentionally require elevated privileges.
"""

import asyncio
import inspect
from typing import Any

import httpx
from supabase import AsyncClient, AsyncClientOptions, create_async_client

from app.config import settings

_async_supabase_client: AsyncClient | None = None
_http_client: httpx.AsyncClient | None = None
_async_client_lock = asyncio.Lock()


async def get_supabase_client() -> AsyncClient:
    """
    Creates and returns a singleton async Supabase admin client.

    WARNING: This client uses the service role key and bypasses Row Level Security.
    All user-scoped queries MUST include explicit `.eq("user_id", ...)` filters
    to prevent cross-tenant data access.
    """
    global _async_supabase_client, _http_client

    if not settings.SUPABASE_URL or not settings.SUPABASE_SECRET_KEY:
        raise ValueError("SUPABASE_URL and SUPABASE_SECRET_KEY must be configured.")

    if _async_supabase_client is None:
        async with _async_client_lock:
            if _async_supabase_client is None:
                # Create httpx client without deprecated parameters
                _http_client = httpx.AsyncClient()
                _async_supabase_client = await create_async_client(
                    settings.SUPABASE_URL,
                    settings.SUPABASE_SECRET_KEY,
                    options=AsyncClientOptions(httpx_client=_http_client),
                )

    return _async_supabase_client


async def close_supabase_client() -> None:
    """Closes the shared httpx client on app shutdown (see lifespan in main.py)."""
    global _async_supabase_client, _http_client

    async with _async_client_lock:
        if _http_client is not None:
            await _http_client.aclose()
            _http_client = None
        _async_supabase_client = None


async def execute_query(builder: Any) -> Any:
    result = builder.execute()
    if inspect.isawaitable(result):
        return await result
    return result
