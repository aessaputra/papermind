"""Unit tests for live model listing filters in model_service."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services import model_service


def _mock_models_response(model_ids: list[str]):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"data": [{"id": m_id} for m_id in model_ids]}
    return resp


@pytest.mark.asyncio
async def test_openai_style_embedding_filter_keeps_jina_ids():
    """Gateway ids without 'embed' (e.g. Jina) must still appear in embedding list."""
    ids = ["jina-ai/jina-embeddings-v5-omni-small", "gpt-4o-mini", ""]
    with patch.object(httpx, "AsyncClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_mock_models_response(ids))
        mock_client_cls.return_value = mock_client
        models = await model_service._fetch_openai_style_models(
            "openai_compatible", "9router-key", "https://9router.aes.my.id/v1", True
        )
    assert "jina-ai/jina-embeddings-v5-omni-small" in models
    assert "gpt-4o-mini" not in models
    assert "" not in models
