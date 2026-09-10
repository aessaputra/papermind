import logging
import math
import uuid
from typing import Any

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.database import execute_query, get_supabase_client
from app.exceptions import RETRYABLE_EXCEPTIONS
from app.schemas import DocumentChunkDTO

logger = logging.getLogger(__name__)

PRESET_CAPS = {
    "off": 0,
    "standard": 75,
    "high": 150,
    "full": 999999,
}

DEFAULT_PRESET = "standard"
MIN_PARAGRAPH_LENGTH = 20


def _validate_uuid(value: str, field_name: str) -> None:
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise ValueError(f"{field_name} must be a valid UUID")


def get_preset_cap(preset: str) -> int:
    return PRESET_CAPS.get(preset, PRESET_CAPS["standard"])


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    dot_product = sum(a * b for a, b in zip(v1, v2))
    norm_v1 = math.sqrt(sum(a * a for a in v1))
    norm_v2 = math.sqrt(sum(b * b for b in v2))
    if norm_v1 == 0 or norm_v2 == 0:
        return 0.0
    return dot_product / (norm_v1 * norm_v2)


class EnrichmentJobService:

    @retry(
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
    )
    async def get_user_preset(self, user_id: str) -> str:
        _validate_uuid(user_id, "user_id")

        try:
            supabase = await get_supabase_client()
            result = await execute_query(
                supabase.table("user_enrichment_configs")
                .select("preset")
                .eq("user_id", user_id)
            )

            if result.data:
                preset = result.data[0].get("preset", DEFAULT_PRESET)
                logger.debug("Retrieved preset '%s' for user %s", preset, user_id)
                return preset

            logger.debug("No preset found for user %s, using default", user_id)
            return DEFAULT_PRESET

        except Exception as exc:
            logger.error("Failed to get user preset for %s: %s", user_id, exc)
            return DEFAULT_PRESET

    @retry(
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
    )
    async def create_job(
        self,
        document_id: str,
        user_id: str,
        total_paragraphs: int,
    ) -> dict[str, Any]:
        _validate_uuid(document_id, "document_id")
        _validate_uuid(user_id, "user_id")

        if total_paragraphs < 0:
            raise ValueError("total_paragraphs must be non-negative")

        try:
            supabase = await get_supabase_client()
            job_data: dict[str, Any] = {
                "document_id": document_id,
                "user_id": user_id,
                "total_paragraphs": total_paragraphs,
            }

            result = await execute_query(
                supabase.table("document_enrichment_jobs").insert(job_data)
            )

            logger.info(
                "Created enrichment job for document %s (user %s, %d paragraphs)",
                document_id,
                user_id,
                total_paragraphs,
            )

            return result.data[0]

        except Exception as exc:
            logger.error(
                "Failed to create enrichment job for document %s: %s", document_id, exc
            )
            raise

    @retry(
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
    )
    async def get_job(self, document_id: str) -> dict[str, Any] | None:
        _validate_uuid(document_id, "document_id")

        try:
            supabase = await get_supabase_client()
            result = await execute_query(
                supabase.table("document_enrichment_jobs")
                .select("*")
                .eq("document_id", document_id)
            )

            if result.data:
                return result.data[0]

            logger.debug("No enrichment job found for document %s", document_id)
            return None

        except Exception as exc:
            logger.error("Failed to get enrichment job for document %s: %s", document_id, exc)
            raise

    @retry(
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
    )
    async def start_job(self, document_id: str, user_id: str) -> None:
        _validate_uuid(document_id, "document_id")
        _validate_uuid(user_id, "user_id")

        try:
            supabase = await get_supabase_client()
            await execute_query(
                supabase.rpc(
                    "start_enrichment_job",
                    {
                        "p_document_id": document_id,
                        "p_user_id": user_id,
                    },
                )
            )

            logger.info("Started enrichment job for document %s", document_id)

        except Exception as exc:
            logger.error("Failed to start enrichment job for document %s: %s", document_id, exc)
            raise

    @retry(
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
    )
    async def update_progress(
        self,
        document_id: str,
        user_id: str,
        processed_paragraphs: int,
        question_chunks_created: int,
    ) -> None:
        _validate_uuid(document_id, "document_id")
        _validate_uuid(user_id, "user_id")

        if processed_paragraphs < 0:
            raise ValueError("processed_paragraphs must be non-negative")
        if question_chunks_created < 0:
            raise ValueError("question_chunks_created must be non-negative")

        try:
            supabase = await get_supabase_client()
            await execute_query(
                supabase.table("document_enrichment_jobs")
                .update(
                    {
                        "processed_paragraphs": processed_paragraphs,
                        "question_chunks_created": question_chunks_created,
                    }
                )
                .eq("document_id", document_id)
                .eq("user_id", user_id)
            )

            logger.debug(
                "Updated progress for document %s: %d/%d paragraphs, %d questions",
                document_id,
                processed_paragraphs,
                question_chunks_created,
                question_chunks_created,
            )

        except Exception as exc:
            logger.warning(
                "Failed to update progress for document %s: %s", document_id, exc
            )

    @retry(
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
    )
    async def complete_job(
        self,
        document_id: str,
        user_id: str,
        processed_paragraphs: int,
        question_chunks_created: int,
    ) -> None:
        _validate_uuid(document_id, "document_id")
        _validate_uuid(user_id, "user_id")

        if processed_paragraphs < 0:
            raise ValueError("processed_paragraphs must be non-negative")
        if question_chunks_created < 0:
            raise ValueError("question_chunks_created must be non-negative")

        try:
            supabase = await get_supabase_client()
            await execute_query(
                supabase.rpc(
                    "complete_enrichment_job",
                    {
                        "p_document_id": document_id,
                        "p_user_id": user_id,
                        "p_processed_paragraphs": processed_paragraphs,
                        "p_question_chunks_created": question_chunks_created,
                    },
                )
            )

            logger.info(
                "Completed enrichment job for document %s: %d paragraphs, %d questions",
                document_id,
                processed_paragraphs,
                question_chunks_created,
            )

        except Exception as exc:
            logger.error(
                "Failed to complete enrichment job for document %s: %s", document_id, exc
            )
            raise

    def select_paragraphs_by_quality(
        self,
        chunks: list[DocumentChunkDTO],
        cap: int,
        min_length: int = MIN_PARAGRAPH_LENGTH,
    ) -> list[DocumentChunkDTO]:
        if cap <= 0:
            return []

        paragraph_chunks = [
            chunk
            for chunk in chunks
            if chunk.metadata.get("type") == "paragraph"
            and len(chunk.content) >= min_length
            and chunk.embedding is not None
        ]
        
        if not paragraph_chunks:
            return []

        dimension = len(paragraph_chunks[0].embedding)  # type: ignore
        centroid = [
            sum(chunk.embedding[i] for chunk in paragraph_chunks) / len(paragraph_chunks)  # type: ignore
            for i in range(dimension)
        ]

        scored_chunks = [
            (chunk, cosine_similarity(chunk.embedding, centroid))  # type: ignore
            for chunk in paragraph_chunks
        ]

        scored_chunks.sort(key=lambda x: x[1], reverse=True)

        selected = [chunk for chunk, _ in scored_chunks[:cap]]

        logger.debug(
            "Selected %d/%d paragraphs for enrichment (cap: %d) using Vector Centroid",
            len(selected),
            len(paragraph_chunks),
            cap,
        )

        return selected