"""
Unit tests for BYOK LLMFactory dynamic provider and embedding model creation
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.crypto_service import CryptoService
from app.services import llm_factory


def test_llm_factory_gemini_creation():
    """Verify LLMFactory creates ChatGoogleGenerativeAI with provided model name."""
    crypto = CryptoService()
    encrypted_key = crypto.encrypt("AIzaSy-test-gemini-key")

    config = {
        "provider": "gemini",
        "api_key_enc": encrypted_key,
        "model_name": "gemini-2.5-flash"
    }

    llm = llm_factory.get_llm_for_config(config)
    assert llm is not None
    assert hasattr(llm, "model")
    assert llm.model == "gemini-2.5-flash"


def test_llm_factory_openai_compatible_creation():
    """Verify LLMFactory creates ChatOpenAI with custom base_url and model_name."""
    crypto = CryptoService()
    encrypted_key = crypto.encrypt("gsk_groq_api_key_123")

    config = {
        "provider": "openai_compatible",
        "api_key_enc": encrypted_key,
        "base_url": "https://api.groq.com/openai/v1",
        "model_name": "llama-3.3-70b-versatile"
    }

    llm = llm_factory.get_llm_for_config(config)
    assert llm is not None
    assert llm.model_name == "llama-3.3-70b-versatile"
    assert str(llm.openai_api_base) == "https://api.groq.com/openai/v1"


def test_llm_factory_openrouter_creation():
    """Verify LLMFactory creates ChatOpenAI pointing to OpenRouter endpoint."""
    crypto = CryptoService()
    encrypted_key = crypto.encrypt("sk-or-v1-key")

    config = {
        "provider": "openrouter",
        "api_key_enc": encrypted_key,
        "model_name": "meta-llama/llama-3-70b"
    }

    llm = llm_factory.get_llm_for_config(config)
    assert llm is not None
    assert llm.model_name == "meta-llama/llama-3-70b"
    assert "openrouter.ai" in str(llm.openai_api_base)


def test_llm_factory_embeddings_creation():
    """Verify LLMFactory creates OpenAIEmbeddings with custom dimensions."""
    crypto = CryptoService()
    encrypted_key = crypto.encrypt("sk-openai-key")

    config = {
        "provider": "openai",
        "api_key_enc": encrypted_key,
        "model_name": "text-embedding-3-small",
        "embedding_dimensions": 1536
    }

    embeddings = llm_factory.get_embeddings_for_config(config)
    assert embeddings is not None
    assert embeddings.model == "text-embedding-3-small"
    assert embeddings.dimensions == 1536


def test_embedding_factory_omits_dimensions_for_openai_compatible_gateway():
    """Gateway-routed models (Jina via 9router) 422 on the dimensions param."""
    crypto = CryptoService()
    encrypted_key = crypto.encrypt("9router-key")

    embeddings = llm_factory.get_embeddings_for_config({
        "provider": "openai_compatible",
        "api_key_enc": encrypted_key,
        "base_url": "https://9router.aes.my.id/v1",
        "model_name": "jina/jina-embeddings-v5-omni-small",
        "embedding_dimensions": 1024,
    })
    assert "dimensions" not in embeddings._invocation_params


def test_embedding_factory_sends_raw_text_for_openai_compatible_gateway():
    """Gateways reject token-id arrays; raw strings must reach the API."""
    import asyncio
    from unittest.mock import MagicMock

    crypto = CryptoService()
    encrypted_key = crypto.encrypt("9router-key")

    embeddings = llm_factory.get_embeddings_for_config({
        "provider": "openai_compatible",
        "api_key_enc": encrypted_key,
        "base_url": "https://9router.aes.my.id/v1",
        "model_name": "jina/jina-embeddings-v5-omni-small",
        "embedding_dimensions": 1024,
    })
    assert embeddings.check_embedding_ctx_length is False

    caps: list[dict] = []

    async def fake_create(**kwargs):
        caps.append(kwargs)
        return {"data": [{"embedding": [0.1] * 1024} for _ in kwargs["input"]],
                "model": "m", "object": "list", "usage": {}}

    embeddings.async_client = MagicMock()
    embeddings.async_client.create = fake_create
    out = asyncio.run(embeddings.aembed_documents(["halo dunia tes pdf"]))
    assert len(out) == 1 and len(out[0]) == 1024
    assert isinstance(caps[0]["input"][0], str)


def test_embedding_factory_omits_dimensions_when_unset():
    """Verify NULL/auto dimensions are omitted so the provider uses model default."""
    crypto = CryptoService()
    encrypted_key = crypto.encrypt("9router-key")

    embeddings = llm_factory.get_embeddings_for_config({
        "provider": "openai_compatible",
        "api_key_enc": encrypted_key,
        "base_url": "https://9router.aes.my.id/v1",
        "model_name": "jina-ai/jina-embeddings-v5-omni-small",
        "embedding_dimensions": None,
    })
    assert "dimensions" not in embeddings._invocation_params


def test_llm_factory_rejects_missing_api_key():
    with pytest.raises(ValueError, match="API key is required"):
        llm_factory.get_llm_for_config({"provider": "openai", "model_name": "gpt-4o-mini"})


def test_embedding_factory_rejects_missing_api_key():
    with pytest.raises(ValueError, match="API key is required"):
        llm_factory.get_embeddings_for_config({"provider": "gemini", "model_name": "models/gemini-embedding-001"})


@pytest.mark.asyncio
async def test_dimension_probe_uses_openrouter_endpoint_and_custom_override():
    """Probe and runtime embeddings must resolve the same provider endpoint."""
    from app.services.model_service import probe_vector_dimension

    for base_url in (None, "https://example.com/v1"):
        with patch.object(llm_factory, "OpenAIEmbeddings") as constructor:
            constructor.return_value.aembed_query = AsyncMock(return_value=[0.1, 0.2])
            assert await probe_vector_dimension("openrouter", "test-key", "test-model", base_url) == 2
            assert constructor.call_args.kwargs["base_url"] == (base_url or "https://openrouter.ai/api/v1")
            constructor.return_value.aembed_query.assert_awaited_once_with("probe")
