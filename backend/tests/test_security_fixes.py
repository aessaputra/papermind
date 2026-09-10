"""Security regression tests for HIGH review findings: upload cap, verify limits."""

from unittest.mock import AsyncMock, patch

from app.config import settings
from app.routers import settings_router


def setup_function(_):
    settings_router._VERIFY_CACHE.clear()
    settings_router._VERIFY_USER_CALLS.clear()


def teardown_function(_):
    settings_router._VERIFY_CACHE.clear()
    settings_router._VERIFY_USER_CALLS.clear()


def test_upload_rejects_oversized_file_with_413(authed_client):
    big = b"%PDF" + b"x" * (settings.MAX_UPLOAD_MB * 1024 * 1024 + 1)
    response = authed_client.post(
        "/api/documents/upload",
        files={"file": ("big.pdf", big, "application/pdf")},
    )
    assert response.status_code == 413


def test_verify_models_rejects_internal_base_url(authed_client):
    response = authed_client.post(
        "/api/settings/providers/verify-models",
        json={"provider": "openai_compatible", "api_key": "sk-test",
              "base_url": "http://169.254.169.254/models"},
    )
    assert response.status_code == 400


def test_verify_models_identical_repeat_served_from_cache(authed_client):
    payload = {"provider": "gemini", "api_key": "bad-key"}
    with patch("app.routers.settings_router.model_service.fetch_available_models",
               new=AsyncMock(return_value={"success": True, "models": ["m"],
                                           "default_model": "m", "error": None})) as mock_fetch:
        first = authed_client.post("/api/settings/providers/verify-models", json=payload)
        second = authed_client.post("/api/settings/providers/verify-models", json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert mock_fetch.await_count == 1


def test_verify_models_rate_limited_after_burst(authed_client):
    with patch("app.routers.settings_router.model_service.fetch_available_models",
               new=AsyncMock(return_value={"success": True, "models": ["m"],
                                           "default_model": "m", "error": None})):
        for i in range(settings_router.VERIFY_MAX_CALLS_PER_MINUTE):
            authed_client.post(
                "/api/settings/providers/verify-models",
                json={"provider": "gemini", "api_key": f"burst-key-{i}"},
            )
        blocked = authed_client.post(
            "/api/settings/providers/verify-models",
            json={"provider": "gemini", "api_key": "burst-key-overflow"},
        )
    assert blocked.status_code == 429


def test_verify_models_distinct_keys_not_rate_limited(authed_client):
    with patch("app.routers.settings_router.model_service.fetch_available_models",
               new=AsyncMock(return_value={"success": True, "models": ["m"],
                                           "default_model": "m", "error": None})):
        first = authed_client.post(
            "/api/settings/providers/verify-models",
            json={"provider": "gemini", "api_key": "key-one"},
        )
        second = authed_client.post(
            "/api/settings/providers/verify-models",
            json={"provider": "gemini", "api_key": "key-two"},
        )
    assert first.status_code == 200
    assert second.status_code == 200
