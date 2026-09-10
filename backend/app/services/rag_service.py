import logging
from collections.abc import AsyncIterable
from typing import Any

from fastapi import HTTPException, status
from fastapi.sse import ServerSentEvent
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel

from app.database import execute_query, get_supabase_client
from app.services import llm_factory, prompt_builder
from app.services.context_retriever import ContextRetriever

logger = logging.getLogger(__name__)


class RAGService:
    def __init__(
        self,
        user_id: str,
        llm: BaseChatModel,
        retriever: ContextRetriever,
    ):
        self.user_id = user_id
        self.llm = llm
        self.retriever = retriever

    async def generate_rag_stream(
        self,
        query: str,
        document_ids: list[str] | None = None,
    ) -> AsyncIterable[ServerSentEvent]:
        chunks = await self.retriever.retrieve_relevant_chunks(
            query=query,
            document_ids=document_ids,
        )

        citations = ContextRetriever.extract_citations(chunks)
        citations_json = [c.model_dump() for c in citations]
        yield ServerSentEvent(data=citations_json, event="citations")

        full_response = ""

        if not chunks:
            no_info_msg = prompt_builder.NO_CONTEXT_MESSAGE
            full_response = no_info_msg
            yield ServerSentEvent(data={"token": no_info_msg}, event="token")
        else:
            prompt = prompt_builder.format_context_prompt(query, chunks)

            async for chunk in self.llm.astream(prompt):
                token_content = chunk.content if hasattr(chunk, "content") else str(chunk)
                if isinstance(token_content, list):
                    token_content = str(token_content)
                if token_content:
                    full_response += token_content
                    yield ServerSentEvent(data={"token": token_content}, event="token")

        yield ServerSentEvent(data={"status": "completed"}, event="done")

        self._last_response = full_response
        self._last_citations = citations_json

    @property
    def last_response(self) -> str:
        return getattr(self, "_last_response", "")

    @property
    def last_citations(self) -> list[dict[str, Any]]:
        return getattr(self, "_last_citations", [])


async def initialize_user_embeddings(user_id: str) -> Embeddings:
    supabase = await get_supabase_client()
    embedding_res = await execute_query(
        supabase.table("user_embedding_configs")
        .select("*")
        .eq("user_id", user_id)
    )

    if not embedding_res.data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Konfigurasi Model Embedding belum diatur. Silakan atur model embedding di menu Settings.",
        )

    return llm_factory.get_embeddings_for_config(embedding_res.data[0])


async def initialize_user_llm(user_id: str, provider: str | None = None) -> BaseChatModel:
    supabase = await get_supabase_client()

    provider_records: list = []
    if provider:
        matched_res = await execute_query(
            supabase.table("user_provider_configs")
            .select("*")
            .eq("user_id", user_id)
            .eq("provider", provider)
        )
        provider_records = matched_res.data if matched_res.data else []

    if not provider_records:
        fallback_res = await execute_query(
            supabase.table("user_provider_configs")
            .select("*")
            .eq("user_id", user_id)
            .order("is_default", desc=True)
            .order("created_at", desc=True)
            .limit(1)
        )
        provider_records = fallback_res.data if fallback_res.data else []

    if not provider_records:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Konfigurasi AI Provider belum diatur. Silakan tambahkan API key Anda di menu Settings.",
        )

    return llm_factory.get_llm_for_config(provider_records[0])


async def initialize_user_models(user_id: str, provider: str | None = None) -> tuple[BaseChatModel, Embeddings]:
    llm = await initialize_user_llm(user_id, provider)
    embeddings_model = await initialize_user_embeddings(user_id)

    return llm, embeddings_model
