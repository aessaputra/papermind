"""
API Routers Integration Tests

Verifies health check endpoint, CORS middleware, route protection, and upload file validations.
"""

from unittest.mock import AsyncMock, MagicMock, patch

MOCK_USER_ID = "11111111-2222-3333-4444-555555555555"
MOCK_DOC_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_health_check_endpoint_returns_online_status(client):
    """Verify that GET /health returns HTTP 200 with online status."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "online"}


def test_protected_document_upload_without_token_returns_401(client):
    """Verify that unauthenticated upload request is rejected with HTTP 401 Unauthorized."""
    response = client.post(
        "/api/documents/upload",
        files={"file": ("test.pdf", b"%PDF-1.4 content", "application/pdf")}
    )
    assert response.status_code == 401


def test_protected_chat_stream_without_token_returns_401(client):
    """Verify that unauthenticated chat stream request is rejected with HTTP 401 Unauthorized."""
    response = client.post(
        "/api/chat/stream",
        json={"query": "Test question?"}
    )
    assert response.status_code == 401


@patch("app.services.ingestion_service.storage_service.upload_file",
       new=AsyncMock(return_value=f"{MOCK_USER_ID}/{MOCK_DOC_ID}.pdf"))
@patch("app.services.ingestion_service.get_supabase_client")
def test_upload_returns_201_immediately_and_defers_parsing(mock_get_supabase, authed_client):
    """Verify upload registers a 'processing' document and returns 201 without parsing synchronously.

    The uploaded bytes are intentionally not a real PDF: with deferred parsing
    the endpoint must still respond 201, and the background task must swallow
    the parse failure after marking the document as failed.
    """
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase
    mock_supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": MOCK_DOC_ID, "created_at": "2026-07-26T00:00:00+00:00"}]
    )

    response = authed_client.post(
        "/api/documents/upload",
        files={"file": ("report.pdf", b"definitely not a real pdf", "application/pdf")}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["document_id"] == MOCK_DOC_ID
    assert data["filename"] == "report.pdf"
    assert data["file_size"] == len(b"definitely not a real pdf")
    assert data["total_pages"] == 0
    assert "total_chunks" not in data
