from typing import Any

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.services.crypto_service import CryptoService


def _resolve_api_key(config: dict[str, Any]) -> str:
    if config.get("api_key"):
        return config["api_key"]

    if config.get("api_key_enc"):
        crypto = CryptoService()
        return crypto.decrypt(config["api_key_enc"])

    return ""


def _resolve_model_name(config: dict[str, Any]) -> str:
    model_name = config.get("model_name")
    if not model_name:
        raise ValueError("Model name is required.")
    return model_name


def get_llm_for_config(config: dict[str, Any]) -> BaseChatModel:
    provider = config.get("provider", "gemini").lower().strip()
    api_key = _resolve_api_key(config)
    model_name = _resolve_model_name(config)
    base_url = config.get("base_url")

    if not api_key:
        raise ValueError(f"API key is required for provider '{provider}'.")

    if provider in ("openai", "openrouter", "openai_compatible"):
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=base_url or ("https://openrouter.ai/api/v1" if provider == "openrouter" else None),
            streaming=True,
        )
    else:
        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=api_key,
            timeout=60,
            streaming=True,
        )


def get_embeddings_for_config(config: dict[str, Any]) -> Embeddings:
    provider = config.get("provider", "gemini").lower().strip()
    api_key = _resolve_api_key(config)
    model_name = _resolve_model_name(config)
    base_url = config.get("base_url")
    dimensions = config.get("embedding_dimensions")

    if not api_key:
        raise ValueError(f"API key is required for provider '{provider}'.")

    if provider in ("openai", "openrouter", "openai_compatible"):
        kwargs: dict[str, Any] = {
            "model": model_name,
            "api_key": api_key,
            "base_url": base_url or ("https://openrouter.ai/api/v1" if provider == "openrouter" else None),
        }
        if provider == "openai_compatible":
            kwargs["check_embedding_ctx_length"] = False
        if provider == "openai_compatible":
            pass
        elif dimensions:
            kwargs["dimensions"] = dimensions
        return OpenAIEmbeddings(**kwargs)

    else:
        kwargs = {
            "model": model_name,
            "google_api_key": api_key,
        }
        if dimensions:
            kwargs["output_dimensionality"] = dimensions
        return GoogleGenerativeAIEmbeddings(**kwargs)
