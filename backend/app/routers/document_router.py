import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile, status

from app.auth import CurrentUserDep
from app.config import settings
from app.database import execute_query, get_supabase_client
from app.schemas import (
    DocumentItemResponse,
    DocumentPreviewResponse,
    DocumentToggleRequest,
    DocumentUploadResponse,
    EnrichmentStatusResponse,
)
from app.services.enrichment_job_service import EnrichmentJobService
from app.services.ingestion_service import PDFIngestionService
from app.services import storage_service as storage_svc

router = APIRouter(
    prefix="/api/documents",
    tags=["Documents"],
)

logger = logging.getLogger(__name__)


@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_pdf_document(
    user: CurrentUserDep,
    file: Annotated[UploadFile, File(...)],
    background_tasks: BackgroundTasks,
) -> DocumentUploadResponse:
    """
    Registers a PDF document and dispatches ingestion to a background task.

    Creates the document row in 'processing' state and uploads the PDF to
    Supabase Storage, then returns 201 immediately. Paragraph
    parsing, embedding, and vector storage run in the background; clients poll
    GET /api/documents to watch the status transition to 'ready' or 'failed'.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files (.pdf) are supported."
        )

    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if file.size is not None and file.size > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File too large. Maximum size is {settings.MAX_UPLOAD_MB} MB."
        )

    pdf_bytes = await file.read()
    if len(pdf_bytes) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File too large. Maximum size is {settings.MAX_UPLOAD_MB} MB."
        )
    if not pdf_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded PDF file is empty."
        )

    ingestion_service = PDFIngestionService()

    try:
        document = await ingestion_service.register_document(
            file.filename,
            len(pdf_bytes),
            user.user_id,
            pdf_bytes,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gagal mendaftarkan dokumen: {e!s}"
        )

    background_tasks.add_task(
        ingestion_service.process_document,
        document_id=document["id"],
        user_id=user.user_id,
        filename=file.filename,
        pdf_bytes=pdf_bytes,
    )

    return DocumentUploadResponse(
        document_id=document["id"],
        filename=file.filename,
        file_size=len(pdf_bytes),
        total_pages=0,
        created_at=document["created_at"],
    )


@router.get("", response_model=list[DocumentItemResponse])
async def list_user_documents(user: CurrentUserDep) -> list[DocumentItemResponse]:
    supabase = await get_supabase_client()
    res = await execute_query(
        supabase.table("documents")
        .select("id, filename, file_size, total_pages, is_active, status, created_at")
        .eq("user_id", user.user_id)
        .order("created_at", desc=True)
    )
    data = res.data if res.data else []

    job_service = EnrichmentJobService()
    documents = []
    for doc in data:
        enrichment_status = None
        job = await job_service.get_job(doc["id"])
        if job:
            enrichment_status = EnrichmentStatusResponse(**{"status": "pending", **job})
        documents.append(DocumentItemResponse(**doc, enrichment=enrichment_status))

    return documents


@router.patch("/{document_id}/toggle", response_model=DocumentItemResponse)
async def toggle_document_active(
    document_id: str,
    body: DocumentToggleRequest,
    user: CurrentUserDep,
) -> DocumentItemResponse:
    supabase = await get_supabase_client()
    res = await execute_query(
        supabase.table("documents")
        .update({"is_active": body.is_active})
        .eq("id", document_id)
        .eq("user_id", user.user_id)
    )
    result = res.data[0] if res.data else None
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found."
        )
    return DocumentItemResponse(**result)


@router.get("/{document_id}/preview", response_model=DocumentPreviewResponse)
async def get_document_preview(
    document_id: str,
    user: CurrentUserDep,
) -> DocumentPreviewResponse:
    supabase = await get_supabase_client()
    res = await execute_query(
        supabase.table("documents")
        .select("id, file_path")
        .eq("id", document_id)
        .eq("user_id", user.user_id)
    )
    if not res.data:
        doc, signed_url = None, None
    else:
        doc = res.data[0]
        file_path = doc.get("file_path")
        signed_url = await storage_svc.create_signed_url(file_path) if file_path else None
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found."
        )
    if signed_url is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PDF file not available in storage."
        )
    return DocumentPreviewResponse(document_id=document_id, signed_url=signed_url)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    user: CurrentUserDep,
) -> None:
    supabase = await get_supabase_client()
    res = await execute_query(
        supabase.table("documents")
        .select("id, file_path")
        .eq("id", document_id)
        .eq("user_id", user.user_id)
    )
    if not res.data:
        found = False
    else:
        file_path = res.data[0].get("file_path")
        if file_path:
            try:
                await storage_svc.delete_file(file_path)
            except Exception:
                logger.warning(
                    "Failed to delete storage file %s during document cleanup",
                    file_path,
                    exc_info=True,
                )
        await execute_query(supabase.table("documents").delete().eq("id", document_id).eq("user_id", user.user_id))
        found = True
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found."
        )
