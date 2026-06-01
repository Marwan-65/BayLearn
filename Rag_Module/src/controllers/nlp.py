"""
NLPController — RAG pipeline orchestrator (composed from mixins)
================================================================

This is the brain of the RAG module. The implementation is split across
small, focused mixins to keep each file readable:

    controllers/_nlp_indexing.py    -> _NLPIndexingMixin
        index_project() -- embed + Qdrant + BM25 + contextual cache

    controllers/_nlp_retrieval.py   -> _NLPRetrievalMixin
        retrieve_sources() -- 7-layer pipeline with ablation flags
        _has_usable_text, _has_math_content helpers

    controllers/_nlp_generation.py  -> _NLPGenerationMixin
        generate_answer_from_sources() -- numbered-context prompt + LLM

    controllers/_nlp_extraction.py  -> _NLPExtractionMixin
        extract_equation_from_sources, extract_animation_params_from_sources

This file defines only the class skeleton (__init__, simple helpers,
validate_project, search, get_vector_db_collection_info) and composes
the mixins via multiple inheritance. To add new behavior, create a new
mixin module and add it to the inheritance list.
"""

import json
import logging

from stores.LLM.LLMEnums import DocumentTypeEnum

from ._nlp_extraction import _NLPExtractionMixin
from ._nlp_generation import _NLPGenerationMixin
from ._nlp_indexing import _NLPIndexingMixin
from ._nlp_retrieval import _NLPRetrievalMixin
from .base import BaseController


class NLPController(
    _NLPIndexingMixin,
    _NLPRetrievalMixin,
    _NLPGenerationMixin,
    _NLPExtractionMixin,
    BaseController,
):
    def __init__(
        self,
        vectordb_client,
        generation_client,
        embedding_client,
        chunk_repository,
        reranker_client=None,
        bm25_client=None,
        contextual_cache=None,
    ):
        super().__init__()
        self.vectordb_client = vectordb_client
        self.generation_client = generation_client
        self.embedding_client = embedding_client
        self.chunk_repository = chunk_repository
        self.reranker_client = reranker_client
        self.bm25_client = bm25_client
        self.contextual_cache = contextual_cache
        self.logger = logging.getLogger(__name__)

    # ==================================================================
    # Simple helpers
    # ==================================================================

    def create_collection_name(self, project_id: str) -> str:
        return f"collection_{project_id}".strip()

    async def validate_project(self, project_id: str):
        # project_id may be a comma-separated list of file ids (multi-select).
        # The project is valid if ANY of the selected files has chunks.
        ids = [p.strip() for p in str(project_id).split(",") if p.strip()]
        for pid in ids or [project_id]:
            chunks = await self.chunk_repository.get_chunks(pid)
            if chunks:
                return {"project_id": project_id}
        return None

    # ==================================================================
    # Legacy single-query search (used by /index/search for debugging)
    # ==================================================================

    def search(self, project_id: str, query: str, limit: int = 5):
        # project_id may be a comma-separated list of file ids (multi-select).
        # Query each file's collection and merge the top results by score.
        ids = [p.strip() for p in str(project_id).split(",") if p.strip()] or [project_id]

        query_vector = self.embedding_client.embed_text(
            text=query,
            document_type=DocumentTypeEnum.QUERY.value,
        )
        if not query_vector:
            return []

        merged = []
        for pid in ids:
            results = self.vectordb_client.search_by_vector(
                collection_name=self.create_collection_name(pid),
                query_vector=query_vector,
                limit=limit,
            )
            if results:
                merged.extend(results)

        if not merged:
            return []

        merged = json.loads(json.dumps(merged, default=lambda x: x.__dict__))
        # Single file: preserve original order. Multiple: sort by score, trim.
        if len(ids) > 1:
            merged.sort(key=lambda r: r.get("score", 0), reverse=True)
            merged = merged[:limit]
        return merged

    def get_vector_db_collection_info(self, project_id: str):
        collection_name = self.create_collection_name(project_id)
        collection_info = self.vectordb_client.get_collection_info(
            collection_name=collection_name
        )
        return json.loads(
            json.dumps(collection_info, default=lambda x: x.__dict__)
        )
