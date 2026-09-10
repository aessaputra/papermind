import asyncio
import logging
import re
import uuid
from typing import Any

import fitz
import pymupdf4llm
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_text_splitters import MarkdownTextSplitter
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from app.database import execute_query, get_supabase_client
from app.exceptions import RETRYABLE_EXCEPTIONS
from app.schemas import DocumentChunkDTO
from app.services.enrichment_job_service import EnrichmentJobService, get_preset_cap
from app.services.rag_service import initialize_user_embeddings, initialize_user_llm
from app.services import storage_service

logger = logging.getLogger(__name__)

QUESTIONS_PER_PARAGRAPH = 5
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

QUESTION_GENERATION_PROMPT = (
    f"Generate {QUESTIONS_PER_PARAGRAPH} diverse questions that can be "
    "answered by this paragraph:\n\n{paragraph_content}\n\n"
    "Some simple query(s) in non-technical language. "
    "Some intermediate query(s) that require some reasoning. "
    "Some advanced query(s) that require deep understanding, using more technical words. "
    "Make sure the questions are clear and concise. "
    "Provide each question on a new line without headings."
)


class PDFIngestionService:
    def __init__(self):
        self.text_splitter = MarkdownTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
        )

    def parse_pdf_to_markdown(self, pdf_bytes: bytes) -> list[dict[str, Any]]:
        doc = fitz.Document(stream=pdf_bytes, filetype="pdf")
        return pymupdf4llm.to_markdown(doc, page_chunks=True)

    def create_chunks_from_pages(
        self, 
        pages: list[dict[str, Any]], 
        filename: str
    ) -> list[DocumentChunkDTO]:
        all_chunks: list[DocumentChunkDTO] = []

        for page_index, page_data in enumerate(pages):
            page_number = page_index + 1
            page_text = page_data.get("text", "").strip()

            if not page_text:
                continue

            text_chunks = self.text_splitter.split_text(page_text)

            for chunk_text in text_chunks:
                cleaned_chunk = chunk_text.strip()
                if not cleaned_chunk:
                    continue

                all_chunks.append(
                    DocumentChunkDTO(
                        id=str(uuid.uuid4()),
                        content=cleaned_chunk,
                        page_number=page_number,
                        filename=filename,
                        metadata={
                            "filename": filename,
                            "page_number": page_number,
                            "type": "paragraph",
                        },
                    )
                )

        return all_chunks

    def parse_pdf_bytes(self, pdf_bytes: bytes, filename: str) -> list[DocumentChunkDTO]:
        pages = self.parse_pdf_to_markdown(pdf_bytes)
        chunks = self.create_chunks_from_pages(pages, filename)

        if not chunks:
            raise ValueError("Could not extract readable text from PDF.")

        return chunks

    @retry(
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        wait=wait_random_exponential(multiplier=2, min=5, max=120),
        stop=stop_after_attempt(10),
    )
    async def generate_questions_batch(
        self, 
        paragraph_content: str, 
        llm: BaseChatModel
    ) -> list[str]:
        prompt = QUESTION_GENERATION_PROMPT.format(
            paragraph_content=paragraph_content
        )

        response = await llm.ainvoke(prompt)
        content = str(response.content) if response.content else ""
        
        questions = []
        for line in content.split('\n'):
            cleaned = re.sub(r'^(\d+\.|[-*+])\s+', '', line.strip())
            if cleaned:
                questions.append(cleaned)
            
        if not questions:
            raise ValueError("LLM did not produce valid synthetic questions.")

        return questions[:QUESTIONS_PER_PARAGRAPH]

    async def register_document(
        self, 
        filename: str, 
        file_size: int, 
        user_id: str, 
        pdf_bytes: bytes
    ) -> dict[str, Any]:
        supabase = await get_supabase_client()

        doc_data: dict[str, Any] = {
            "user_id": user_id,
            "filename": filename,
            "file_size": file_size,
            "total_pages": 0,
            "status": "processing",
            "is_active": True,
        }

        doc_response = await execute_query(
            supabase.table("documents").insert(doc_data)
        )
        document_record = doc_response.data[0]
        document_id = document_record["id"]

        try:
            file_path = await storage_service.upload_file(
                user_id, document_id, pdf_bytes
            )
        except Exception:
            await execute_query(
                supabase.table("documents")
                .delete()
                .eq("id", document_id)
                .eq("user_id", user_id)
            )
            raise

        await execute_query(
            supabase.table("documents")
            .update({"file_path": file_path})
            .eq("id", document_id)
        )

        document_record["file_path"] = file_path
        return document_record

    async def process_document(
        self,
        document_id: str,
        user_id: str,
        filename: str,
        pdf_bytes: bytes,
        batch_size: int = 100,
    ) -> None:
        supabase = await get_supabase_client()
        job_service = EnrichmentJobService()

        try:
            chunks = await asyncio.to_thread(self.parse_pdf_bytes, pdf_bytes, filename)

            embeddings_model = await initialize_user_embeddings(user_id)

            await self._store_chunks_with_embeddings(
                supabase, document_id, user_id, chunks, embeddings_model, batch_size
            )

            total_pages = max(chunk.page_number for chunk in chunks)
            await execute_query(
                supabase.table("documents")
                .update({"status": "ready", "total_pages": total_pages})
                .eq("id", document_id)
            )

            logger.info(
                "Document %s processed: %d chunks stored.", document_id, len(chunks)
            )

            await self._enrich_document_if_enabled(
                supabase,
                document_id,
                user_id,
                chunks,
                embeddings_model,
                batch_size,
                job_service,
            )

        except Exception:
            logger.exception("Document %s processing failed.", document_id)
            await execute_query(
                supabase.table("documents")
                .update({"status": "failed"})
                .eq("id", document_id)
            )

    async def _enrich_document_if_enabled(
        self,
        supabase: Any,
        document_id: str,
        user_id: str,
        chunks: list[DocumentChunkDTO],
        embeddings_model: Embeddings,
        batch_size: int,
        job_service: EnrichmentJobService,
    ) -> None:
        try:
            preset = await job_service.get_user_preset(user_id)
            cap = get_preset_cap(preset)

            if cap > 0:
                await job_service.create_job(
                    document_id=document_id,
                    user_id=user_id,
                    total_paragraphs=len(
                        [c for c in chunks if c.metadata.get("type") == "paragraph"]
                    ),
                )

                llm = await initialize_user_llm(user_id)
                await self.enrich_document_with_questions(
                    supabase,
                    document_id,
                    user_id,
                    chunks,
                    llm,
                    embeddings_model,
                    job_service,
                    cap,
                    batch_size,
                )
        except Exception:
            logger.exception("Document %s question enrichment failed.", document_id)

    async def enrich_document_with_questions(
        self,
        supabase: Any,
        document_id: str,
        user_id: str,
        chunks: list[DocumentChunkDTO],
        llm: BaseChatModel,
        embeddings_model: Embeddings,
        job_service: EnrichmentJobService,
        cap: int,
        batch_size: int = 100,
    ) -> None:
        await job_service.start_job(document_id, user_id)

        paragraph_chunks = job_service.select_paragraphs_by_quality(chunks, cap)
        total_paragraphs = len(paragraph_chunks)

        question_chunks: list[DocumentChunkDTO] = []
        processed_count = 0
        failed_count = 0
        
        semaphore = asyncio.Semaphore(3)

        async def process_chunk(chunk: DocumentChunkDTO) -> list[DocumentChunkDTO]:
            nonlocal processed_count, failed_count
            async with semaphore:
                try:
                    questions = await self.generate_questions_batch(chunk.content, llm)
                    processed_count += 1
                    
                    if processed_count % 10 == 0:
                        await job_service.update_progress(
                            document_id=document_id,
                            user_id=user_id,
                            processed_paragraphs=processed_count,
                            question_chunks_created=len(question_chunks),
                        )
                        
                    return [
                        DocumentChunkDTO(
                            id=str(uuid.uuid4()),
                            parent_chunk_id=chunk.id,
                            content=chunk.content,
                            page_number=chunk.page_number,
                            filename=chunk.filename,
                            metadata={
                                **chunk.metadata,
                                "type": "question",
                                "question": q,
                            },
                        )
                        for q in questions
                    ]
                except Exception as exc:
                    logger.warning(
                        "Skipping question enrichment for chunk %s: %s", chunk.id, exc
                    )
                    failed_count += 1
                    return []

        tasks = [process_chunk(chunk) for chunk in paragraph_chunks]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for res in results:
            if isinstance(res, list):
                question_chunks.extend(res)

        if question_chunks:
            await self._store_chunks_with_embeddings(
                supabase, document_id, user_id, question_chunks, embeddings_model, batch_size
            )

        await job_service.complete_job(
            document_id=document_id,
            user_id=user_id,
            processed_paragraphs=processed_count,
            question_chunks_created=len(question_chunks),
        )

        logger.info(
            "Document %s enrichment completed: %d/%d paragraphs, %d questions, %d failed.",
            document_id,
            processed_count,
            total_paragraphs,
            len(question_chunks),
            failed_count,
        )

    async def _store_chunks_with_embeddings(
        self,
        supabase: Any,
        document_id: str,
        user_id: str,
        chunks: list[DocumentChunkDTO],
        embeddings_model: Embeddings,
        batch_size: int,
    ) -> None:
        chunk_texts = [
            chunk.metadata.get("question", chunk.content)
            if chunk.metadata.get("type") == "question"
            else chunk.content
            for chunk in chunks
        ]

        vector_embeddings = await embeddings_model.aembed_documents(chunk_texts)

        for chunk, embedding_vector in zip(chunks, vector_embeddings):
            chunk.embedding = embedding_vector

        chunk_records = [
            {
                "id": chunk.id,
                "parent_chunk_id": chunk.parent_chunk_id,
                "document_id": document_id,
                "user_id": user_id,
                "content": chunk.content,
                "page_number": chunk.page_number,
                "metadata": chunk.metadata,
                "embedding": chunk.embedding,
            }
            for chunk in chunks
        ]

        for i in range(0, len(chunk_records), batch_size):
            batch = chunk_records[i : i + batch_size]
            await execute_query(supabase.table("document_chunks").insert(batch))

