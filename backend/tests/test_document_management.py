"""
Tests for Document Management endpoints and StorageService.
Covers toggle, preview, delete, and schema serialization.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.schemas import (
    DocumentItemResponse,
    DocumentToggleRequest,
)

MOCK_USER_ID = "11111111-2222-3333-4444-555555555555"
MOCK_DOC_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
MOCK_FILE_PATH = f"{MOCK_USER_ID}/{MOCK_DOC_ID}.pdf"


# --- Schema DTO Tests ---


def test_document_item_response_serialization():
    """Verify DocumentItemResponse serializes all document management fields."""
    dto = DocumentItemResponse(
        id=MOCK_DOC_ID,
        filename="report.pdf",
        file_size=102400,
        total_pages=5,
        is_active=True,
        status="ready",
        created_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
    )
    data = dto.model_dump()
    assert data["id"] == MOCK_DOC_ID
    assert data["is_active"] is True
    assert data["status"] == "ready"


def test_document_toggle_request_validation():
    """Verify DocumentToggleRequest accepts boolean is_active."""
    req = DocumentToggleRequest(is_active=False)
    assert req.is_active is False


# --- API Endpoint Tests ---


@patch("app.routers.document_router.EnrichmentJobService")
@patch("app.routers.document_router.get_supabase_client")
def test_list_documents_returns_items(mock_get_supabase, mock_job_service_cls, authed_client):
    """Verify GET /api/documents returns list of DocumentItemResponse."""
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase
    mock_job_service = MagicMock()
    mock_job_service.get_job = AsyncMock(return_value={
        "status": "completed",
        "total_paragraphs": 10,
        "processed_paragraphs": 10,
        "question_chunks_created": 50,
        "failed_paragraphs": 0,
    })
    mock_job_service_cls.return_value = mock_job_service

    mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
        data=[
            {
                "id": MOCK_DOC_ID,
                "filename": "report.pdf",
                "file_size": 102400,
                "total_pages": 5,
                "is_active": True,
                "status": "ready",
                "created_at": "2026-07-24T00:00:00+00:00",
            }
        ]
    )

    response = authed_client.get("/api/documents")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == MOCK_DOC_ID
    assert data[0]["is_active"] is True
    assert data[0]["status"] == "ready"
    assert data[0]["enrichment"]["status"] == "completed"
    assert data[0]["enrichment"]["question_chunks_created"] == 50


@patch("app.routers.document_router.get_supabase_client")
def test_toggle_document_active(mock_get_supabase, authed_client):
    """Verify PATCH /api/documents/{id}/toggle updates is_active and returns document."""
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase

    mock_supabase.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[
            {
                "id": MOCK_DOC_ID,
                "filename": "report.pdf",
                "file_size": 102400,
                "total_pages": 5,
                "is_active": False,
                "status": "ready",
                "created_at": "2026-07-24T00:00:00+00:00",
            }
        ]
    )

    response = authed_client.patch(
        f"/api/documents/{MOCK_DOC_ID}/toggle",
        json={"is_active": False},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_active"] is False


@patch("app.routers.document_router.get_supabase_client")
def test_toggle_document_not_found(mock_get_supabase, authed_client):
    """Verify PATCH /api/documents/{id}/toggle returns 404 for non-existent document."""
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase

    mock_supabase.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[]
    )

    response = authed_client.patch(
        f"/api/documents/{MOCK_DOC_ID}/toggle",
        json={"is_active": True},
    )
    assert response.status_code == 404


@patch("app.routers.document_router.storage_svc")
@patch("app.routers.document_router.get_supabase_client")
def test_delete_document_with_storage_cleanup(mock_get_supabase, mock_storage, authed_client):
    """Verify DELETE /api/documents/{id} deletes from storage and database."""
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase

    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": MOCK_DOC_ID, "file_path": MOCK_FILE_PATH}]
    )
    mock_storage.delete_file = AsyncMock()

    response = authed_client.delete(f"/api/documents/{MOCK_DOC_ID}")
    assert response.status_code == 204
    mock_storage.delete_file.assert_called_once_with(MOCK_FILE_PATH)


@patch("app.routers.document_router.get_supabase_client")
def test_delete_document_not_found(mock_get_supabase, authed_client):
    """Verify DELETE /api/documents/{id} returns 404 for non-existent document."""
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase

    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[]
    )

    response = authed_client.delete(f"/api/documents/{MOCK_DOC_ID}")
    assert response.status_code == 404


@patch("app.routers.document_router.storage_svc")
@patch("app.routers.document_router.get_supabase_client")
def test_preview_document_returns_signed_url(mock_get_supabase, mock_storage, authed_client):
    """Verify GET /api/documents/{id}/preview returns signed URL."""
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase

    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": MOCK_DOC_ID, "file_path": MOCK_FILE_PATH}]
    )
    mock_storage.create_signed_url = AsyncMock(return_value="https://storage.example.com/signed-url")

    response = authed_client.get(f"/api/documents/{MOCK_DOC_ID}/preview")
    assert response.status_code == 200
    data = response.json()
    assert data["signed_url"] == "https://storage.example.com/signed-url"
    assert data["document_id"] == MOCK_DOC_ID
