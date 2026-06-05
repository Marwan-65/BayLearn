"""
this file is the RAG pipeline orchestrator , The implementation is split across
focused mixins to keep each file readable: n2sem el file elkbeer
    _nlp_indexing.py    -> _NLPIndexingMixin
        index_project() -> embed + Qdrant + BM25 + contextual cache
    _nlp_retrieval.py   -> _NLPRetrievalMixin
        retrieve_sources() -- 7-layer pipeline with ablation flags
        _has_usable_text, _has_math_content helpers
    _nlp_generation.py  -> _NLPGenerationMixin
        generate_answer_from_sources() -- numbered-context prompt + LLM
    _nlp_extraction.py  -> _NLPExtractionMixin
        extract_equation_from_sources
"""

import json
import logging
from stores.LLM.LLMEnums import DocumentTypeEnum
from ._nlp_extraction import _NLPExtractionMixin
from ._nlp_generation import _NLPGenerationMixin
from ._nlp_indexing import _NLPIndexingMixin
from ._nlp_retrieval import _NLPRetrievalMixin
from .base import BaseController

class NLPController(_NLPIndexingMixin,_NLPRetrievalMixin,_NLPGenerationMixin,
    _NLPExtractionMixin,BaseController,):
    # applied here dependency injection
    def __init__(self,vectordb_client,generation_client,embedding_client,
        reranker_client=None,bm25_client=None,contextual_cache=None,):
        super().__init__()
        self.vectordb_client = vectordb_client
        self.generation_client = generation_client
        self.embedding_client = embedding_client
        self.reranker_client = reranker_client
        self.bm25_client = bm25_client
        self.contextual_cache = contextual_cache
        self.logger = logging.getLogger(__name__)
        
    # standardizes vector DB collection naming per project
    # ensures isolation between different uploaded datasets
    def create_collection_name(self, project_id: str) -> str:
        return f"collection_{project_id}".strip()

    # assures that at least 1 collection has at least non-empty vector index
    async def validate_project(self, project_id: str):
        ids = [p.strip() for p in str(project_id).split(",") if p.strip()]
        for pid in ids or [project_id]:
            collection_name = self.create_collection_name(pid)
            if not self.vectordb_client.is_collection_exists(collection_name):
                continue
            info = self.vectordb_client.get_collection_info(collection_name)
            if not info:
                continue
            count = getattr(info, "points_count", None)
            if count is None:
                count = getattr(info, "vectors_count", 0) or 0
            if count > 0:
                return {"project_id": project_id}
        return None
    # simple searching across embeddings 
    def search(self, project_id: str, query: str, limit: int = 5):
        ids = [p.strip() for p in str(project_id).split(",") if p.strip()] or [project_id]
        query_vector = self.embedding_client.embed_text(
            text=query,document_type=DocumentTypeEnum.QUERY.value,)
        if not query_vector:
            return []
        merged = []
        for pid in ids:
            results = self.vectordb_client.search_by_vector(
                collection_name=self.create_collection_name(pid),query_vector=query_vector,limit=limit,)
            if results:
                merged.extend(results)
        if not merged:
            return []
        merged = json.loads(json.dumps(merged, default=lambda x: x.__dict__))
        if len(ids) > 1:
            merged.sort(key=lambda r: r.get("score", 0), reverse=True)
            merged = merged[:limit]
        return merged

    def get_vector_db_collection_info(self, project_id: str):
        collection_name = self.create_collection_name(project_id)
        collection_info = self.vectordb_client.get_collection_info(
            collection_name=collection_name)
        return json.loads(json.dumps(collection_info, default=lambda x: x.__dict__))
