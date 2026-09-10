"""
RAG Service Tests

Verifies prompt context assembly, citation metadata extraction, and SSE streaming event generation.
Tests adapted for the decomposed module structure: ContextRetriever, PromptBuilder, RAGService.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas import Citation
from app.services.context_retriever import ContextRetriever
from app.services import prompt_builder
from app.services.rag_service import RAGService

# ── Shared Fixtures ─────────────────────────────────────────────────

MOCK_CHUNKS = [
    {"content": "First chunk content about RAG.", "metadata": {"filename": "doc1.pdf", "page_number": 2}},
    {"content": "Second chunk content about Supabase.", "metadata": {"filename": "doc2.pdf", "page_number": 5}},
]


# ── Existing Tests (updated assertions) ─────────────────────────────

def test_format_context_prompt_should_include_page_numbers_and_content():
    """Verify that PromptBuilder formats retrieved vector chunks into structured context."""
    prompt_messages = prompt_builder.format_context_prompt(query="What is RAG?", chunks=MOCK_CHUNKS)
    prompt = "".join(msg.content for msg in prompt_messages)

    assert "First chunk content about RAG." in prompt
    assert "Halaman: 2" in prompt
    assert "Second chunk content about Supabase." in prompt
    assert "Halaman: 5" in prompt
    assert "What is RAG?" in prompt


def test_extract_citations_should_return_valid_citation_dtos():
    """Verify that ContextRetriever.extract_citations builds valid Citation DTO objects."""
    mock_chunks = [
        {"content": "Sample content snippet for testing citation extractions.", "metadata": {"filename": "paper.pdf", "page_number": 12}}
    ]

    citations = ContextRetriever.extract_citations(mock_chunks)

    assert len(citations) == 1
    assert isinstance(citations[0], Citation)
    assert citations[0].filename == "paper.pdf"
    assert citations[0].page_number == 12
    assert "Sample content" in citations[0].content


@pytest.mark.asyncio
async def test_generate_rag_stream_emits_valid_sse_events():
    """Verify that RAGService.generate_rag_stream yields ServerSentEvent objects for citations and tokens."""
    # Mock LLM
    mock_llm = MagicMock()

    async def mock_astream(_prompt):
        yield MagicMock(content="Hello ")
        yield MagicMock(content="world!")

    mock_llm.astream = mock_astream

    mock_retriever = MagicMock()
    mock_retriever.retrieve_relevant_chunks = AsyncMock(return_value=[
        {"content": "Mock text for SSE stream test.", "metadata": {"filename": "test.pdf", "page_number": 1}}
    ])

    service = RAGService(
        user_id="12345678-1234-1234-1234-123456789012",
        llm=mock_llm,
        retriever=mock_retriever,
    )

    events = []
    async for event in service.generate_rag_stream(query="Test query"):
        events.append(event)

    assert len(events) >= 3

    # Verify first SSE event is citations
    assert events[0].event == "citations"

    # Verify token events contain expected content
    token_events = [e for e in events if e.event == "token"]
    token_data = [e.data for e in token_events]
    assert any("Hello" in str(d) for d in token_data)
    assert any("world!" in str(d) for d in token_data)

    # Verify last event is done
    assert events[-1].event == "done"


@pytest.mark.asyncio
async def test_context_retriever_awaits_async_embedding_and_rpc():
    embeddings = MagicMock()
    embeddings.aembed_query = AsyncMock(return_value=[0.1, 0.2])

    rpc_result = MagicMock(data=[])
    rpc_builder = MagicMock()
    rpc_builder.execute = AsyncMock(return_value=rpc_result)
    supabase = MagicMock()
    supabase.rpc.return_value = rpc_builder

    with patch("app.services.context_retriever.get_supabase_client", AsyncMock(return_value=supabase)):
        retriever = ContextRetriever(embeddings_model=embeddings, user_id="user-1")
        chunks = await retriever.retrieve_relevant_chunks("apa itu rag?")

    assert chunks == []
    embeddings.aembed_query.assert_awaited_once_with("apa itu rag?")
    rpc_builder.execute.assert_awaited_once()




@pytest.mark.asyncio
async def test_context_retriever_awaits_awaitable_embedding_wrapper():
    embeddings = MagicMock()

    async def async_embed_query(_query):
        await asyncio.sleep(0)
        return [0.1, 0.2]

    embeddings.aembed_query = lambda query: async_embed_query(query)

    rpc_result = MagicMock(data=[])
    rpc_builder = MagicMock()
    rpc_builder.execute = AsyncMock(return_value=rpc_result)
    supabase = MagicMock()
    supabase.rpc.return_value = rpc_builder

    with patch("app.services.context_retriever.get_supabase_client", AsyncMock(return_value=supabase)):
        retriever = ContextRetriever(embeddings_model=embeddings, user_id="user-1")
        chunks = await retriever.retrieve_relevant_chunks("apa itu rag?")

    assert chunks == []
    embeddings.embed_query.assert_not_called()


# ── New Tests: Prompt Engineering Patterns ───────────────────────────

def test_system_prompt_contains_cot_reasoning_steps():
    """Verify system prompt includes chain-of-thought reasoning guidance."""
    system = prompt_builder.SYSTEM_INSTRUCTION

    assert "IDENTIFY" in system
    assert "ANALYZE" in system
    assert "SYNTHESIZE" in system
    assert "VERIFY" in system


def test_system_prompt_contains_verification_step():
    """Verify system prompt instructs LLM to verify answers against context."""
    system = prompt_builder.SYSTEM_INSTRUCTION

    assert "VERIFY" in system
    assert "claim" in system.lower()
    assert "context" in system.lower()


def test_system_prompt_contains_confidence_strategy():
    """Verify system prompt includes confidence-based response strategy."""
    system = prompt_builder.SYSTEM_INSTRUCTION

    assert "FULL" in system
    assert "PARTIAL" in system
    assert "NO RELEVANT" in system


def test_context_formatting_includes_source_labels():
    """Verify context uses 'Sumber [n]' source labels with visual separators."""
    prompt_messages = prompt_builder.format_context_prompt(query="Test?", chunks=MOCK_CHUNKS)
    prompt = "".join(msg.content for msg in prompt_messages)

    assert "Sumber [1]" in prompt
    assert "Sumber [2]" in prompt
    assert "---" in prompt


def test_no_context_message_is_accessible():
    """Verify NO_CONTEXT_MESSAGE constant is still accessible."""
    assert prompt_builder.NO_CONTEXT_MESSAGE
    assert "tidak ditemukan" in prompt_builder.NO_CONTEXT_MESSAGE.lower()


def test_build_context_string_handles_missing_metadata():
    """Verify _build_context_string gracefully handles chunks with missing metadata."""
    sparse_chunks = [
        {"content": "Content without metadata."},
        {"content": "Content with partial metadata.", "metadata": {"filename": "partial.pdf"}},
    ]
    result = prompt_builder._build_context_string(sparse_chunks)

    assert "Content without metadata." in result
    assert "Content with partial metadata." in result
    assert "Sumber [1]" in result
    assert "Sumber [2]" in result


def test_merge_contexts_combines_adjacent_paragraphs():
    """Verify that _merge_contexts merges adjacent chunks from the same document and page."""
    retriever = ContextRetriever(embeddings_model=MagicMock(), user_id="test")
    chunks = [
        {
            "document_id": "doc1",
            "content": "Line 1-5",
            "metadata": {"page_number": 1, "line_start": 1, "line_end": 5}
        },
        {
            "document_id": "doc1",
            "content": "Line 6-10",
            "metadata": {"page_number": 1, "line_start": 6, "line_end": 10}
        },
        {
            "document_id": "doc1",
            "content": "Line 20-25",
            "metadata": {"page_number": 1, "line_start": 20, "line_end": 25}
        }
    ]
    
    merged = retriever._merge_contexts(chunks)
    
    assert len(merged) == 2
    assert merged[0]["content"] == "Line 1-5\n\nLine 6-10"
    assert merged[0]["metadata"]["line_start"] == 1
    assert merged[0]["metadata"]["line_end"] == 10
    
    assert merged[1]["content"] == "Line 20-25"
    assert merged[1]["metadata"]["line_start"] == 20
    assert merged[1]["metadata"]["line_end"] == 25


def test_merge_contexts_deduplicates_exact_chunks():
    """Verify that _merge_contexts deduplicates chunks with the same coordinates."""
    retriever = ContextRetriever(embeddings_model=MagicMock(), user_id="test")
    chunks = [
        {
            "document_id": "doc1",
            "content": "Same content",
            "metadata": {"page_number": 1, "line_start": 1, "line_end": 5}
        },
        {
            "document_id": "doc1",
            "content": "Same content again from another question match",
            "metadata": {"page_number": 1, "line_start": 1, "line_end": 5}
        }
    ]
    
    merged = retriever._merge_contexts(chunks)
    
    assert len(merged) == 1
    assert merged[0]["content"] == "Same content"
