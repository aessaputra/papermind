from unittest.mock import MagicMock, patch

import pytest

from app.services.enrichment_job_service import EnrichmentJobService, get_preset_cap

MOCK_USER_ID = "11111111-2222-3333-4444-555555555555"
MOCK_DOC_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _make_supabase_mock() -> tuple[MagicMock, dict[str, MagicMock]]:
    tables = {
        name: MagicMock()
        for name in (
            "documents",
            "document_chunks",
            "user_embedding_configs",
            "user_provider_configs",
            "document_enrichment_jobs",
            "user_enrichment_configs",
        )
    }
    supabase = MagicMock()
    supabase.table.side_effect = lambda name: tables[name]
    supabase.rpc = MagicMock()
    return supabase, tables


@pytest.mark.asyncio
@patch("app.services.enrichment_job_service.get_supabase_client")
async def test_create_job_should_insert_pending_record(mock_get_supabase):
    mock_supabase, tables = _make_supabase_mock()
    mock_get_supabase.return_value = mock_supabase

    tables["document_enrichment_jobs"].insert.return_value.execute.return_value = MagicMock(
        data=[{
            "id": "job-123",
            "document_id": MOCK_DOC_ID,
            "user_id": MOCK_USER_ID,
            "status": "pending",
            "total_paragraphs": 10,
            "processed_paragraphs": 0,
            "question_chunks_created": 0,
            "failed_paragraphs": 0,
            "attempt_count": 0,
        }]
    )

    service = EnrichmentJobService()
    job = await service.create_job(document_id=MOCK_DOC_ID, user_id=MOCK_USER_ID, total_paragraphs=10)

    assert job["status"] == "pending"
    assert job["total_paragraphs"] == 10
    assert job["attempt_count"] == 0

    insert_call = tables["document_enrichment_jobs"].insert.call_args
    inserted_data = insert_call[0][0]
    assert inserted_data["document_id"] == MOCK_DOC_ID
    assert inserted_data["user_id"] == MOCK_USER_ID
    assert set(inserted_data) == {"document_id", "user_id", "total_paragraphs"}
    assert inserted_data["total_paragraphs"] == 10


@pytest.mark.asyncio
@patch("app.services.enrichment_job_service.get_supabase_client")
async def test_create_job_should_validate_uuid_format(mock_get_supabase):
    service = EnrichmentJobService()

    with pytest.raises(ValueError, match="document_id must be a valid UUID"):
        await service.create_job(document_id="invalid-uuid", user_id=MOCK_USER_ID, total_paragraphs=10)

    with pytest.raises(ValueError, match="user_id must be a valid UUID"):
        await service.create_job(document_id=MOCK_DOC_ID, user_id="invalid-uuid", total_paragraphs=10)


@pytest.mark.asyncio
@patch("app.services.enrichment_job_service.get_supabase_client")
async def test_create_job_should_validate_total_paragraphs(mock_get_supabase):
    service = EnrichmentJobService()

    with pytest.raises(ValueError, match="total_paragraphs must be non-negative"):
        await service.create_job(document_id=MOCK_DOC_ID, user_id=MOCK_USER_ID, total_paragraphs=-1)


@pytest.mark.asyncio
@patch("app.services.enrichment_job_service.get_supabase_client")
async def test_get_job_should_return_job_record(mock_get_supabase):
    mock_supabase, tables = _make_supabase_mock()
    mock_get_supabase.return_value = mock_supabase

    tables["document_enrichment_jobs"].select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{
            "id": "job-123",
            "document_id": MOCK_DOC_ID,
            "user_id": MOCK_USER_ID,
            "status": "running",
        }]
    )

    service = EnrichmentJobService()
    job = await service.get_job(document_id=MOCK_DOC_ID)

    assert job is not None
    assert job["document_id"] == MOCK_DOC_ID
    assert job["status"] == "running"


@pytest.mark.asyncio
@patch("app.services.enrichment_job_service.get_supabase_client")
async def test_get_job_should_return_none_when_not_found(mock_get_supabase):
    mock_supabase, tables = _make_supabase_mock()
    mock_get_supabase.return_value = mock_supabase

    tables["document_enrichment_jobs"].select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[]
    )

    service = EnrichmentJobService()
    job = await service.get_job(document_id=MOCK_DOC_ID)

    assert job is None


@pytest.mark.asyncio
@patch("app.services.enrichment_job_service.get_supabase_client")
async def test_update_progress_should_increment_counts(mock_get_supabase):
    mock_supabase, tables = _make_supabase_mock()
    mock_get_supabase.return_value = mock_supabase

    tables["document_enrichment_jobs"].update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{
            "id": "job-123",
            "processed_paragraphs": 5,
            "question_chunks_created": 25,
        }]
    )

    service = EnrichmentJobService()
    await service.update_progress(
        document_id=MOCK_DOC_ID,
        user_id=MOCK_USER_ID,
        processed_paragraphs=5,
        question_chunks_created=25,
    )

    update_call = tables["document_enrichment_jobs"].update.call_args
    update_data = update_call[0][0]
    assert update_data["processed_paragraphs"] == 5
    assert update_data["question_chunks_created"] == 25


@pytest.mark.asyncio
@patch("app.services.enrichment_job_service.get_supabase_client")
async def test_start_job_should_call_rpc_function(mock_get_supabase):
    mock_supabase, tables = _make_supabase_mock()
    mock_get_supabase.return_value = mock_supabase

    mock_supabase.rpc.return_value.execute.return_value = MagicMock(data=[])

    service = EnrichmentJobService()
    await service.start_job(document_id=MOCK_DOC_ID, user_id=MOCK_USER_ID)

    mock_supabase.rpc.assert_called_once_with(
        "start_enrichment_job",
        {
            "p_document_id": MOCK_DOC_ID,
            "p_user_id": MOCK_USER_ID,
        }
    )


@pytest.mark.asyncio
@patch("app.services.enrichment_job_service.get_supabase_client")
async def test_complete_job_should_call_rpc_function(mock_get_supabase):
    mock_supabase, tables = _make_supabase_mock()
    mock_get_supabase.return_value = mock_supabase

    mock_supabase.rpc.return_value.execute.return_value = MagicMock(data=[])

    service = EnrichmentJobService()
    await service.complete_job(
        document_id=MOCK_DOC_ID,
        user_id=MOCK_USER_ID,
        processed_paragraphs=10,
        question_chunks_created=50,
    )

    mock_supabase.rpc.assert_called_once_with(
        "complete_enrichment_job",
        {
            "p_document_id": MOCK_DOC_ID,
            "p_user_id": MOCK_USER_ID,
            "p_processed_paragraphs": 10,
            "p_question_chunks_created": 50,
        }
    )


def test_get_enrichment_cap_should_return_preset_values():
    assert get_preset_cap("off") == 0
    assert get_preset_cap("standard") == 75
    assert get_preset_cap("high") == 150
    assert get_preset_cap("full") == 999999
    assert get_preset_cap("unknown") == 75


@pytest.mark.asyncio
@patch("app.services.enrichment_job_service.get_supabase_client")
async def test_get_user_preset_should_return_user_configured_preset(mock_get_supabase):
    mock_supabase, tables = _make_supabase_mock()
    mock_get_supabase.return_value = mock_supabase

    tables["user_enrichment_configs"].select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"preset": "high"}]
    )

    service = EnrichmentJobService()
    preset = await service.get_user_preset(user_id=MOCK_USER_ID)

    assert preset == "high"


@pytest.mark.asyncio
@patch("app.services.enrichment_job_service.get_supabase_client")
async def test_get_user_preset_should_default_to_standard_when_not_configured(mock_get_supabase):
    mock_supabase, tables = _make_supabase_mock()
    mock_get_supabase.return_value = mock_supabase

    tables["user_enrichment_configs"].select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[]
    )

    service = EnrichmentJobService()
    preset = await service.get_user_preset(user_id=MOCK_USER_ID)

    assert preset == "standard"


def test_select_paragraphs_by_quality_should_use_centroid_scoring():
    from app.schemas import DocumentChunkDTO

    chunks = [
        DocumentChunkDTO(
            id="outlier-chunk",
            content="This paragraph talks about something completely unrelated to the main topic.",
            page_number=1,
            filename="test.pdf",
            metadata={"type": "paragraph"},
            embedding=[-1.0, -1.0],
        ),
        DocumentChunkDTO(
            id="core-chunk-1",
            content="This is the main theme of the document. Very important.",
            page_number=1,
            filename="test.pdf",
            metadata={"type": "paragraph"},
            embedding=[0.9, 0.9],
        ),
        DocumentChunkDTO(
            id="core-chunk-2",
            content="Another paragraph discussing the core concepts.",
            page_number=1,
            filename="test.pdf",
            metadata={"type": "paragraph"},
            embedding=[1.0, 1.0],
        ),
    ]

    service = EnrichmentJobService()
    # Centroid of [-1,-1], [0.9,0.9], [1,1] is roughly [0.63, 0.63]
    # The two core chunks will have high cosine similarity to [0.63, 0.63]
    # The outlier will have negative similarity.
    selected = service.select_paragraphs_by_quality(chunks, cap=2)

    assert len(selected) == 2
    selected_ids = {chunk.id for chunk in selected}
    assert "core-chunk-1" in selected_ids
    assert "core-chunk-2" in selected_ids
    assert "outlier-chunk" not in selected_ids


def test_select_paragraphs_by_quality_should_skip_very_short_paragraphs():
    from app.schemas import DocumentChunkDTO

    chunks = [
        DocumentChunkDTO(
            id="tiny-1",
            content="x",
            page_number=1,
            filename="test.pdf",
            metadata={"type": "paragraph"},
            embedding=[1.0, 1.0],
        ),
        DocumentChunkDTO(
            id="good-1",
            content="This paragraph has enough content to be considered valuable for enrichment.",
            page_number=1,
            filename="test.pdf",
            metadata={"type": "paragraph"},
            embedding=[1.0, 1.0],
        ),
    ]

    service = EnrichmentJobService()
    selected = service.select_paragraphs_by_quality(chunks, cap=10, min_length=20)

    assert len(selected) == 1
    assert selected[0].id == "good-1"


def test_select_paragraphs_by_quality_should_filter_by_type_and_missing_embedding():
    from app.schemas import DocumentChunkDTO

    chunks = [
        DocumentChunkDTO(
            id="para-1",
            content="A paragraph chunk with sufficient length to pass the minimum threshold.",
            page_number=1,
            filename="test.pdf",
            metadata={"type": "paragraph"},
            embedding=[1.0, 0.0],
        ),
        DocumentChunkDTO(
            id="question-1",
            content="A question chunk that should be ignored despite having enough length.",
            page_number=1,
            filename="test.pdf",
            metadata={"type": "question"},
            embedding=[1.0, 0.0],
        ),
        DocumentChunkDTO(
            id="missing-embedding",
            content="This paragraph has no embedding so it must be skipped.",
            page_number=1,
            filename="test.pdf",
            metadata={"type": "paragraph"},
            embedding=None,
        ),
    ]

    service = EnrichmentJobService()
    selected = service.select_paragraphs_by_quality(chunks, cap=10)

    assert len(selected) == 1
    assert selected[0].id == "para-1"


def test_select_paragraphs_by_quality_should_return_empty_when_cap_is_zero():
    from app.schemas import DocumentChunkDTO

    chunks = [
        DocumentChunkDTO(
            id="para-1",
            content="Some content here",
            page_number=1,
            filename="test.pdf",
            metadata={"type": "paragraph"},
            embedding=[1.0, 1.0],
        ),
    ]

    service = EnrichmentJobService()
    selected = service.select_paragraphs_by_quality(chunks, cap=0)

    assert len(selected) == 0