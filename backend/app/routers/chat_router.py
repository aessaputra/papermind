import json
import logging
from collections.abc import AsyncIterable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import ValidationError

from app.auth import CurrentUserDep
from app.database import execute_query, get_supabase_client
from app.schemas import (
    ChatMessageResponse,
    ChatQueryRequest,
    ChatSessionResponse,
    Citation,
)
from app.services.context_retriever import ContextRetriever
from app.services.rag_service import RAGService, initialize_user_models

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/chat",
    tags=["Chat"],
)


def parse_citations(citations_raw: Any) -> list[Citation]:
    if not citations_raw:
        return []
    if isinstance(citations_raw, str):
        try:
            citations_raw = json.loads(citations_raw)
        except Exception as e:
            logger.debug("Failed to parse citations JSON: %s", e)
            return []
    if isinstance(citations_raw, list):
        parsed = []
        for item in citations_raw:
            if isinstance(item, dict):
                try:
                    parsed.append(Citation.model_validate(item))
                except ValidationError as e:
                    logger.debug("Skipped invalid citation: %s", e)
        return parsed
    return []


async def get_rag_service(
    user: CurrentUserDep,
    request: ChatQueryRequest,
) -> RAGService:
    llm, embeddings_model = await initialize_user_models(
        user_id=user.user_id,
        provider=request.provider,
    )
    retriever = ContextRetriever(
        embeddings_model=embeddings_model,
        user_id=user.user_id,
    )
    return RAGService(
        user_id=user.user_id,
        llm=llm,
        retriever=retriever,
    )


RAGServiceDep = Annotated[RAGService, Depends(get_rag_service)]


async def _stream_with_session(
    service: RAGService,
    request: ChatQueryRequest,
    user_id: str,
) -> AsyncIterable[ServerSentEvent]:
    active_session_id = request.session_id
    try:
        supabase = await get_supabase_client()
        if not active_session_id:
            title = request.query[:30] + ("…" if len(request.query) > 30 else "")
            sess_res = await execute_query(supabase.table("chat_sessions").insert({
                "user_id": user_id,
                "title": title,
            }))
            if sess_res.data:
                active_session_id = str(sess_res.data[0]["id"])
    except Exception as e:
        logger.warning("Failed to create chat session for user %s: %s", user_id, e, exc_info=True)

    if active_session_id:
        yield ServerSentEvent(data={"session_id": active_session_id}, event="session")

    async for event in service.generate_rag_stream(
        query=request.query,
        document_ids=request.document_ids,
    ):
        yield event

    if active_session_id and service.last_response:
        try:
            supabase = await get_supabase_client()
            await execute_query(supabase.table("chat_messages").insert([
                {
                    "session_id": active_session_id,
                    "user_id": user_id,
                    "sender": "user",
                    "content": request.query,
                    "citations": [],
                },
                {
                    "session_id": active_session_id,
                    "user_id": user_id,
                    "sender": "assistant",
                    "content": service.last_response,
                    "citations": service.last_citations,
                },
            ]))
        except Exception as e:
            logger.warning(
                "Failed to persist chat messages for session %s: %s",
                active_session_id, e,
                exc_info=True,
            )


@router.post("/stream", response_class=EventSourceResponse)
async def stream_chat_response(
    request: ChatQueryRequest,
    user: CurrentUserDep,
    service: RAGServiceDep,
) -> AsyncIterable[ServerSentEvent]:
    async for event in _stream_with_session(service, request, user.user_id):
        yield event


@router.get("/sessions", response_model=list[ChatSessionResponse])
async def list_chat_sessions(user: CurrentUserDep) -> list[ChatSessionResponse]:
    supabase = await get_supabase_client()
    response = await execute_query(
        supabase.table("chat_sessions")
        .select("*")
        .eq("user_id", user.user_id)
        .order("created_at", desc=True)
    )
    records = response.data if response.data else []
    return [
        ChatSessionResponse(
            id=str(r["id"]),
            title=r.get("title", "Percakapan"),
            created_at=str(r["created_at"]),
        )
        for r in records
    ]


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageResponse])
async def list_session_messages(
    session_id: str,
    user: CurrentUserDep,
) -> list[ChatMessageResponse]:
    supabase = await get_supabase_client()
    response = await execute_query(
        supabase.table("chat_messages")
        .select("*")
        .eq("session_id", session_id)
        .eq("user_id", user.user_id)
        .order("created_at", desc=False)
    )
    records = response.data if response.data else []
    return [
        ChatMessageResponse(
            id=str(r["id"]),
            session_id=str(r["session_id"]),
            sender=r["sender"],
            content=r["content"],
            citations=parse_citations(r.get("citations")),
            created_at=str(r["created_at"]),
        )
        for r in records
    ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat_session(session_id: str, user: CurrentUserDep) -> None:
    supabase = await get_supabase_client()
    existing = await execute_query(
        supabase.table("chat_sessions").select("id").eq("id", session_id).eq("user_id", user.user_id)
    )
    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found."
        )
    await execute_query(supabase.table("chat_sessions").delete().eq("id", session_id).eq("user_id", user.user_id))
