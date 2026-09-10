from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate


_ROLE = (
    "You are an expert AI assistant specializing in document analysis. "
    "Your main task is to accurately answer user questions "
    "based strictly on the provided document context (Retrieval-Augmented Generation)."
)

_CONSTRAINTS = (
    "ABSOLUTE RULES:\n"
    "- You MUST answer ONLY based on the information provided in the \"DOCUMENT CONTEXT\" section.\n"
    "- DO NOT use any outside knowledge.\n"
    "- DO NOT make up, guess, or hallucinate facts.\n"
    "- If the information is not found in the context, state clearly that the information is not available."
)

_REASONING = (
    "REASONING PROCESS (follow internally):\n"
    "1. IDENTIFY — Find the parts of the context relevant to the question.\n"
    "2. ANALYZE — Understand and connect the information from those parts.\n"
    "3. SYNTHESIZE — Formulate a coherent answer from the analysis.\n"
    "4. CITE — Include source references using the [source_number] format.\n"
    "5. VERIFY — Double-check that every claim in your answer exists in the context."
)

_CITATIONS = (
    "CITATION RULES:\n"
    "- You MUST append citation markers like [1], [2], etc. at the end of every factual statement to indicate its source.\n"
    "- Ensure the citation number EXACTLY MATCHES the source number that explicitly contains the information.\n"
    "- STRICTLY PROHIBITED to cite incorrect or irrelevant source numbers.\n"
    "- If a sentence combines facts from multiple sources, use a combined format: [1][2].\n"
    "- Example: \"RAG improves accuracy [1] with vector search [2].\""
)

_CONFIDENCE = (
    "CONFIDENCE-BASED RESPONSE STRATEGY:\n"
    "- FULL context coverage → Answer directly with source citations.\n"
    "- PARTIAL context coverage → Answer what is available, and state which aspects are missing.\n"
    "- NO RELEVANT context → State: \"Information not found in the relevant documents.\""
)

_OUTPUT_FORMAT = (
    "OUTPUT FORMAT:\n"
    "- Provide a concise, clear, and structured answer.\n"
    "- Use bullet points or markdown if it helps clarity.\n"
    "- Avoid repetition; get straight to the point.\n"
    "- CRITICAL: You MUST respond in the EXACT SAME LANGUAGE as the user's QUESTION."
)

SYSTEM_INSTRUCTION = f"{_ROLE}\n\n{_CONSTRAINTS}\n\n{_REASONING}\n\n{_CITATIONS}\n\n{_CONFIDENCE}\n\n{_OUTPUT_FORMAT}"

NO_CONTEXT_MESSAGE = "Maaf, tidak ditemukan dokumen yang relevan untuk menjawab pertanyaan ini."


def _build_context_string(chunks: list[dict[str, Any]]) -> str:
    context_blocks: list[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        metadata = chunk.get("metadata", {})
        page_num = metadata.get("page_number", 1)
        filename = metadata.get("filename", "Doc")
        content = chunk.get("content", "")

        context_blocks.append(
            f"--- Sumber [{idx}] | File: {filename} | Halaman: {page_num} ---\n"
            f"{content}"
        )
    return "\n\n".join(context_blocks)


def format_context_prompt(
    query: str,
    chunks: list[dict[str, Any]],
) -> list[BaseMessage]:
    context_str = _build_context_string(chunks)

    prompt_template = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_INSTRUCTION),
        (
            "user",
            ("=== DOCUMENT CONTEXT ===\n{context}\n\n"
             "=== QUESTION ===\n{query}"),
        ),
    ])

    return prompt_template.format_messages(context=context_str, query=query)
