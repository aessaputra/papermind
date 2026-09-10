from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserPayload(BaseModel):
    user_id: str
    email: EmailStr
    role: str = "authenticated"

    model_config = ConfigDict(frozen=True)


class Citation(BaseModel):
    filename: str
    page_number: int
    content: str


class ChatMessageResponse(BaseModel):
    id: str
    session_id: str
    sender: str
    content: str
    citations: list[Citation] = []
    created_at: datetime


class DocumentChunkDTO(BaseModel):
    id: str | None = None
    parent_chunk_id: str | None = None
    content: str
    page_number: int
    filename: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] | None = None


class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    file_size: int
    total_pages: int
    created_at: datetime


class EnrichmentStatusResponse(BaseModel):
    status: str
    total_paragraphs: int = 0
    processed_paragraphs: int = 0
    question_chunks_created: int = 0
    failed_paragraphs: int = 0


class DocumentItemResponse(BaseModel):
    id: str
    filename: str
    file_size: int
    total_pages: int
    is_active: bool = True
    status: str = "ready"
    created_at: datetime
    enrichment: EnrichmentStatusResponse | None = None


class DocumentToggleRequest(BaseModel):
    is_active: bool


class DocumentPreviewResponse(BaseModel):
    document_id: str
    signed_url: str


class ChatSessionResponse(BaseModel):
    id: str
    title: str
    created_at: datetime


ProviderType = Literal["gemini", "openai", "openrouter", "openai_compatible"]


class ChatQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000, description="User question prompt")
    provider: ProviderType | None = Field("gemini", description="LLM provider name")
    document_ids: list[str] | None = Field(None, max_length=20, description="Optional document ID filters")
    session_id: str | None = Field(None, description="Optional chat session ID")



class ProviderConfigCreate(BaseModel):
    provider: ProviderType
    api_key: str = Field(min_length=1, description="Raw API key string")
    display_name: str | None = Field(None, max_length=100, description="Custom label e.g. Groq Llama 3")
    base_url: str | None = Field(None, max_length=500, description="Custom base URL endpoint")
    model_name: str = Field(min_length=1, max_length=200, description="Target model slug name")
    is_default: bool = Field(False, description="Set as active default chat provider")

    def model_post_init(self, __context: Any, /) -> None:
        if self.provider == "openai_compatible" and not self.base_url:
            raise ValueError("base_url is required for OpenAI-Compatible provider")


class ProviderConfigUpdate(BaseModel):
    display_name: str | None = Field(None, max_length=100)
    api_key: str | None = Field(None, min_length=1, description="New raw API key if rotating")
    base_url: str | None = Field(None, max_length=500)
    model_name: str | None = Field(None, min_length=1, max_length=200)
    is_default: bool | None = None


class ProviderConfigResponse(BaseModel):
    id: str
    provider: str
    display_name: str | None = None
    base_url: str | None = None
    model_name: str | None = None
    is_default: bool


class EmbeddingConfigSaveRequest(BaseModel):
    provider: str = Field(description="Provider name: gemini, openai, openrouter, or openai_compatible")
    api_key: str | None = Field(None, description="Raw API key string (optional if reusing provider key)")
    base_url: str | None = Field(None, max_length=500)
    model_name: str = Field(min_length=1, description="Embedding model name slug")
    embedding_dimensions: int | None = Field(None, gt=0, description="Vector output dimensions (omit for auto-detect)")


class EmbeddingConfigResponse(BaseModel):
    provider: str
    base_url: str | None = None
    model_name: str
    embedding_dimensions: int | None
    locked: bool


EnrichmentPreset = Literal["off", "standard", "high", "full"]


class EnrichmentConfigRequest(BaseModel):
    preset: EnrichmentPreset


class EnrichmentConfigResponse(BaseModel):
    preset: EnrichmentPreset
    max_enriched_paragraphs: int


class VerifyModelsRequest(BaseModel):
    provider: str = Field(..., description="Provider type: gemini, openai, openrouter, or openai_compatible")
    model_type: Literal["chat", "embedding"] = Field("chat", description="Model type filter: chat or embedding")
    api_key: str | None = Field(None, description="Raw API key to test")
    base_url: str | None = Field(None, max_length=500, description="Optional custom base URL")
    config_id: str | None = Field(None, description="Optional existing ProviderConfig ID to reuse saved encrypted key")


class VerifyModelsResponse(BaseModel):
    success: bool
    models: list[str]
    default_model: str
    probed_dimension: int | None = None
    error: str | None = None




