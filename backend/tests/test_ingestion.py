"""
PDF Ingestion Service Tests

Verifies LangChain-based chunking, question generation, and background document processing.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas import DocumentChunkDTO
from app.services.ingestion_service import PDFIngestionService


def test_markdown_chunking_should_split_text_into_chunks():
    """Verify MarkdownTextSplitter creates chunks from markdown text."""
    ingestion_service = PDFIngestionService()
    
    pages = [
        {
            "text": "# Introduction\n\nThis is the first paragraph.\n\nThis is the second paragraph.",
            "metadata": {"page": 1}
        }
    ]
    
    chunks = ingestion_service.create_chunks_from_pages(pages, "test_doc.pdf")
    
    assert len(chunks) > 0
    for chunk in chunks:
        assert isinstance(chunk, DocumentChunkDTO)
        assert chunk.filename == "test_doc.pdf"
        assert chunk.page_number == 1
        assert chunk.metadata["filename"] == "test_doc.pdf"
        assert chunk.metadata["page_number"] == 1
        assert chunk.metadata["type"] == "paragraph"


def test_markdown_chunking_should_skip_empty_pages():
    """Verify that empty pages produce no chunks."""
    ingestion_service = PDFIngestionService()
    
    pages = [
        {"text": "   \n\n  ", "metadata": {"page": 1}}
    ]
    
    chunks = ingestion_service.create_chunks_from_pages(pages, "empty.pdf")
    assert len(chunks) == 0


def test_pdf_parsing_should_extract_text_from_pages():
    """Verify PDF parsing extracts text from multiple pages."""
    ingestion_service = PDFIngestionService()
    
    pdf_bytes = _build_pdf_with_text([
        ["Page 1 content line 1", "Page 1 content line 2"],
        ["Page 2 content line 1", "Page 2 content line 2"],
    ])
    
    chunks = ingestion_service.parse_pdf_bytes(pdf_bytes, "test.pdf")
    
    assert len(chunks) > 0
    page_numbers = {chunk.page_number for chunk in chunks}
    assert 1 in page_numbers
    assert 2 in page_numbers


@pytest.mark.asyncio
async def test_generate_questions_should_parse_structured_output():
    """Verify LLM response yields questions using structured output."""
    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(
        content="Apa itu RAG?\nBagaimana RAG meningkatkan akurasi?\nApa peran vektor dalam RAG?\nKapan RAG digunakan?\nMengapa RAG membutuhkan embedding?"
    ))
    
    ingestion_service = PDFIngestionService()
    questions = await ingestion_service.generate_questions_batch(
        "Paragraf tentang RAG.", mock_llm
    )
    
    assert len(questions) == 5
    assert questions[0] == "Apa itu RAG?"
    assert questions[1] == "Bagaimana RAG meningkatkan akurasi?"
    assert questions[2] == "Apa peran vektor dalam RAG?"
    assert questions[3] == "Kapan RAG digunakan?"
    assert questions[4] == "Mengapa RAG membutuhkan embedding?"


@pytest.mark.asyncio
async def test_generate_questions_should_raise_on_unparseable_llm_output():
    """Verify an empty or question-less LLM response is treated as generation failure."""
    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="   \n \n"))
    
    ingestion_service = PDFIngestionService()
    with pytest.raises(ValueError):
        await ingestion_service.generate_questions_batch(
            "Paragraf tentang RAG.", mock_llm
        )


MOCK_USER_ID = "11111111-2222-3333-4444-555555555555"
MOCK_DOC_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _build_pdf_with_text(pages: list[list[str]]) -> bytes:
    """Builds a minimal valid PDF where each inner list is one page of text lines."""
    font_obj_id = 3 + 2 * len(pages)
    kid_refs = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))

    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: f"<< /Type /Pages /Kids [{kid_refs}] /Count {len(pages)} >>".encode(),
        font_obj_id: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }

    for i, lines in enumerate(pages):
        text_ops = ["BT /F1 12 Tf 72 720 Td"]
        for j, line in enumerate(lines):
            if j > 0:
                text_ops.append("0 -28 Td")
            text_ops.append(f"({line}) Tj")
        text_ops.append("ET")
        stream = "\n".join(text_ops).encode("latin-1")

        objects[3 + 2 * i] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_obj_id} 0 R >> >> /Contents {4 + 2 * i} 0 R >>"
        ).encode()
        objects[4 + 2 * i] = (
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for obj_id in sorted(objects):
        offsets[obj_id] = len(pdf)
        pdf += f"{obj_id} 0 obj\n".encode() + objects[obj_id] + b"\nendobj\n"
    xref_pos = len(pdf)
    max_id = max(objects)
    pdf += f"xref\n0 {max_id + 1}\n".encode()
    pdf += b"0000000000 65535 f \n"
    for obj_id in range(1, max_id + 1):
        pdf += f"{offsets[obj_id]:010d} 00000 n \n".encode()
    pdf += (
        f"trailer\n<< /Size {max_id + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF"
    ).encode()
    return bytes(pdf)


def _make_supabase_mock() -> tuple[MagicMock, dict[str, MagicMock]]:
    tables = {name: MagicMock() for name in ("documents", "document_chunks", "user_embedding_configs", "user_provider_configs")}
    supabase = MagicMock()
    supabase.table.side_effect = lambda name: tables[name]
    return supabase, tables


def _configure_embedding_config(tables: dict[str, MagicMock]) -> None:
    tables["user_embedding_configs"].select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"provider": "gemini", "model_name": "models/text-embedding-004", "embedding_dimensions": 768}]
    )


@pytest.mark.asyncio
@patch("app.services.llm_factory.get_embeddings_for_config")
@patch("app.services.rag_service.get_supabase_client")
@patch("app.services.ingestion_service.get_supabase_client")
async def test_process_document_should_embed_chunks_and_mark_document_ready(
    mock_get_supabase, mock_rag_supabase, mock_get_embeddings
):
    """Verify background processing stores chunks with embeddings."""
    mock_supabase, tables = _make_supabase_mock()
    mock_get_supabase.return_value = mock_supabase
    mock_rag_supabase.return_value = mock_supabase
    _configure_embedding_config(tables)

    mock_embeddings = MagicMock()
    mock_embeddings.aembed_documents = AsyncMock(return_value=[[0.1, 0.2, 0.3]])
    mock_get_embeddings.return_value = mock_embeddings

    pdf_bytes = _build_pdf_with_text([["Test paragraph text."]])

    ingestion_service = PDFIngestionService()
    with patch("app.services.enrichment_job_service.EnrichmentJobService.get_user_preset", AsyncMock(return_value="off")):
        await ingestion_service.process_document(
            document_id=MOCK_DOC_ID,
            user_id=MOCK_USER_ID,
            filename="paper.pdf",
            pdf_bytes=pdf_bytes,
        )

    inserted_records = tables["document_chunks"].insert.call_args[0][0]
    assert len(inserted_records) >= 1

    first_record = inserted_records[0]
    assert first_record["document_id"] == MOCK_DOC_ID
    assert first_record["user_id"] == MOCK_USER_ID
    assert first_record["page_number"] == 1
    assert first_record["metadata"]["type"] == "paragraph"

    mock_embeddings.aembed_documents.assert_awaited()
    tables["documents"].update.assert_called_with({"status": "ready", "total_pages": 1})


@pytest.mark.asyncio
@patch("app.services.llm_factory.get_embeddings_for_config")
@patch("app.services.rag_service.get_supabase_client")
@patch("app.services.ingestion_service.get_supabase_client")
async def test_process_document_should_mark_failed_when_embedding_fails(
    mock_get_supabase, mock_rag_supabase, mock_get_embeddings
):
    """Verify embedding failures mark the document failed."""
    mock_supabase, tables = _make_supabase_mock()
    mock_get_supabase.return_value = mock_supabase
    mock_rag_supabase.return_value = mock_supabase
    _configure_embedding_config(tables)

    mock_embeddings = MagicMock()
    mock_embeddings.aembed_documents = AsyncMock(side_effect=Exception("429 Too Many Requests"))
    mock_get_embeddings.return_value = mock_embeddings

    pdf_bytes = _build_pdf_with_text([["Test paragraph text."]])

    ingestion_service = PDFIngestionService()
    await ingestion_service.process_document(
        document_id=MOCK_DOC_ID,
        user_id=MOCK_USER_ID,
        filename="paper.pdf",
        pdf_bytes=pdf_bytes,
    )

    tables["documents"].update.assert_called_with({"status": "failed"})
    tables["document_chunks"].insert.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.ingestion_service.EnrichmentJobService")
async def test_enrich_document_with_questions_should_store_linked_question_chunks(
    mock_job_service_class,
):
    mock_supabase, tables = _make_supabase_mock()

    mock_job_service = MagicMock()
    mock_job_service_class.return_value = mock_job_service
    mock_job_service.start_job = AsyncMock()
    mock_job_service.update_progress = AsyncMock()
    mock_job_service.complete_job = AsyncMock()
    mock_job_service.get_user_preset = AsyncMock(return_value="standard")
    mock_job_service.get_preset_cap = MagicMock(return_value=75)
    mock_job_service.select_paragraphs_by_quality = lambda chunks, cap: [
        DocumentChunkDTO(
            id="paragraph-1",
            content="Test paragraph text with enough length to pass minimum threshold.",
            page_number=1,
            filename="paper.pdf",
            metadata={
                "filename": "paper.pdf",
                "page_number": 1,
                "type": "paragraph",
            },
        )
    ]

    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(
        content="What is this?\nWhy does it matter?"
    ))

    mock_embeddings = MagicMock()
    mock_embeddings.aembed_documents = AsyncMock(return_value=[[0.1, 0.2], [0.3, 0.4]])

    ingestion_service = PDFIngestionService()
    await ingestion_service.enrich_document_with_questions(
        supabase=mock_supabase,
        document_id=MOCK_DOC_ID,
        user_id=MOCK_USER_ID,
        chunks=[],
        llm=mock_llm,
        embeddings_model=mock_embeddings,
        job_service=mock_job_service,
        cap=75,
    )

    inserted_records = tables["document_chunks"].insert.call_args[0][0]
    assert len(inserted_records) == 2
    
    questions = [record["metadata"]["question"] for record in inserted_records]
    assert "What is this?" in questions
    assert "Why does it matter?" in questions
    
    for record in inserted_records:
        assert record["parent_chunk_id"] == "paragraph-1"
        assert "Test paragraph text" in record["content"]
        assert record["metadata"]["type"] == "question"


@pytest.mark.asyncio
@patch("app.services.ingestion_service.EnrichmentJobService")
async def test_enrich_document_with_questions_should_skip_failed_paragraphs_and_continue(
    mock_job_service_class,
):
    mock_supabase, tables = _make_supabase_mock()

    chunks = [
        DocumentChunkDTO(
            id="paragraph-1",
            content="Broken paragraph with enough length to pass threshold.",
            page_number=1,
            filename="paper.pdf",
            metadata={"filename": "paper.pdf", "page_number": 1, "type": "paragraph"},
        ),
        DocumentChunkDTO(
            id="paragraph-2",
            content="Working paragraph with enough length to pass threshold.",
            page_number=1,
            filename="paper.pdf",
            metadata={"filename": "paper.pdf", "page_number": 1, "type": "paragraph"},
        ),
    ]

    mock_job_service = MagicMock()
    mock_job_service_class.return_value = mock_job_service
    mock_job_service.start_job = AsyncMock()
    mock_job_service.update_progress = AsyncMock()
    mock_job_service.complete_job = AsyncMock()
    mock_job_service.get_user_preset = AsyncMock(return_value="standard")
    mock_job_service.get_preset_cap = MagicMock(return_value=75)
    mock_job_service.select_paragraphs_by_quality = lambda c, cap: chunks

    mock_llm = AsyncMock()
    
    call_count = [0]
    async def mock_ainvoke(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise Exception("401 Unauthorized")
        return MagicMock(content="What works?")
    
    mock_llm.ainvoke = mock_ainvoke

    mock_embeddings = MagicMock()
    mock_embeddings.aembed_documents = AsyncMock(return_value=[[0.1, 0.2]])

    ingestion_service = PDFIngestionService()
    await ingestion_service.enrich_document_with_questions(
        supabase=mock_supabase,
        document_id=MOCK_DOC_ID,
        user_id=MOCK_USER_ID,
        chunks=chunks,
        llm=mock_llm,
        embeddings_model=mock_embeddings,
        job_service=mock_job_service,
        cap=75,
    )

    inserted_records = tables["document_chunks"].insert.call_args[0][0]
    assert len(inserted_records) == 1
    assert inserted_records[0]["parent_chunk_id"] == "paragraph-2"
    assert inserted_records[0]["metadata"]["question"] == "What works?"


@pytest.mark.asyncio
@patch("app.services.ingestion_service.EnrichmentJobService")
async def test_enrich_document_with_questions_should_respect_cap_parameter(
    mock_job_service_class,
):
    mock_supabase, tables = _make_supabase_mock()

    chunks = [
        DocumentChunkDTO(
            id=f"paragraph-{index}",
            content=f"Paragraph {index} with enough length to pass minimum threshold for selection.",
            page_number=1,
            filename="paper.pdf",
            metadata={"filename": "paper.pdf", "page_number": 1, "type": "paragraph"},
        )
        for index in range(100)
    ]

    mock_job_service = MagicMock()
    mock_job_service_class.return_value = mock_job_service
    mock_job_service.start_job = AsyncMock()
    mock_job_service.update_progress = AsyncMock()
    mock_job_service.complete_job = AsyncMock()
    mock_job_service.select_paragraphs_by_quality = lambda c, cap: chunks[:cap]

    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(
        content="What is this?"
    ))

    mock_embeddings = MagicMock()
    mock_embeddings.aembed_documents = AsyncMock(return_value=[[0.1, 0.2]] * 75)

    ingestion_service = PDFIngestionService()
    await ingestion_service.enrich_document_with_questions(
        supabase=mock_supabase,
        document_id=MOCK_DOC_ID,
        user_id=MOCK_USER_ID,
        chunks=chunks,
        llm=mock_llm,
        embeddings_model=mock_embeddings,
        batch_size=1000,
        job_service=mock_job_service,
        cap=75,
    )

    inserted_records = tables["document_chunks"].insert.call_args[0][0]
    assert len(inserted_records) == 75
    assert inserted_records[-1]["parent_chunk_id"] == "paragraph-74"


@pytest.mark.asyncio
@patch("app.services.ingestion_service.get_supabase_client")
async def test_process_document_should_mark_document_failed_on_unparsable_pdf(
    mock_get_supabase,
):
    """Verify background processing marks the document failed instead of raising."""
    mock_supabase, tables = _make_supabase_mock()
    mock_get_supabase.return_value = mock_supabase

    ingestion_service = PDFIngestionService()
    await ingestion_service.process_document(
        document_id=MOCK_DOC_ID,
        user_id=MOCK_USER_ID,
        filename="broken.pdf",
        pdf_bytes=b"this is not a real pdf",
    )

    tables["documents"].update.assert_called_with({"status": "failed"})
    tables["document_chunks"].insert.assert_not_called()
