import json
import logging
from typing import Any

from langchain_core.embeddings import Embeddings

from app.database import execute_query, get_supabase_client
from app.schemas import Citation

logger = logging.getLogger(__name__)

class ContextRetriever:

    def __init__(self, embeddings_model: Embeddings, user_id: str):
        self.embeddings_model = embeddings_model
        self.user_id = user_id

    def _merge_contexts(self, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unique_results = {}
        for r in chunks:
            meta = r.get('metadata', {})
            key = (r.get('document_id'), meta.get('page_number'), meta.get('line_start'), meta.get('line_end'))
            if key not in unique_results:
                unique_results[key] = r
        deduped = list(unique_results.values())
        deduped.sort(key=lambda x: (
            x.get('document_id', ''),
            x.get('metadata', {}).get('page_number', 0),
            x.get('metadata', {}).get('line_start', 0)
        ))
        merged: list[dict[str, Any]] = []
        for r in deduped:
            if not merged:
                merged.append(r)
                continue
            prev = merged[-1]
            prev_meta = prev.get('metadata', {})
            r_meta = r.get('metadata', {})
            if (prev.get('document_id') == r.get('document_id') and
                prev_meta.get('page_number') == r_meta.get('page_number') and
                prev_meta.get('line_end', 0) >= r_meta.get('line_start', 0) - 2):
                prev['content'] += "\n\n" + r.get('content', '')
                prev_meta['line_end'] = max(prev_meta.get('line_end', 0), r_meta.get('line_end', 0))
            else:
                merged.append(r)
        return merged

    async def retrieve_relevant_chunks(self, query: str, top_k: int=4, fetch_k: int=20, lambda_mult: float=0.5, document_ids: list[str] | None=None) -> list[dict[str, Any]]:
        supabase = await get_supabase_client()
        query_embedding = await self.embeddings_model.aembed_query(query)
        rpc_params = {'query_embedding': query_embedding, 'match_count': fetch_k, 'filter_user_id': self.user_id}
        response = await execute_query(supabase.rpc('match_document_chunks', rpc_params))
        results = response.data if response.data else []
        if document_ids:
            results = [r for r in results if r.get('document_id') in document_ids]
        if not results:
            return []
        if 'embedding' not in results[0]:
            logger.warning("RPC 'match_document_chunks' did not return 'embedding'. Falling back to Dense Retrieval without MMR.")
            return self._merge_contexts(results[:top_k])
        import numpy as np
        from langchain_community.vectorstores.utils import maximal_marginal_relevance

        def parse_embedding(emb: Any) -> list[float]:
            if isinstance(emb, str):
                return json.loads(emb)
            return emb
        candidate_embeddings = [parse_embedding(r['embedding']) for r in results]
        mmr_indices = maximal_marginal_relevance(np.array(query_embedding), candidate_embeddings, k=top_k, lambda_mult=lambda_mult)
        final_results = [results[i] for i in mmr_indices]
        return self._merge_contexts(final_results)

    @staticmethod
    def extract_citations(chunks: list[dict[str, Any]]) -> list[Citation]:
        citations: list[Citation] = []
        for chunk in chunks:
            metadata = chunk.get('metadata', {})
            citations.append(Citation(
                filename=metadata.get('filename', 'Unknown Document'), 
                page_number=metadata.get('page_number', 1), 
                content=chunk.get('content', '')
            ))
        return citations
