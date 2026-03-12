import json
from typing import List
from stores.LLM.LLMEnums import DocumentTypeEnum
from .base import BaseController
import logging


class NLPController(BaseController):

    def __init__(
        self,
        vectordb_client,
        generation_client,
        embedding_client,
        chunk_repository,
    ):
        super().__init__()
        self.vectordb_client = vectordb_client
        self.generation_client = generation_client
        self.embedding_client = embedding_client
        self.chunk_repository = chunk_repository
        self.logger = logging.getLogger(__name__)

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------

    def create_collection_name(self, project_id: str):
        return f"collection_{project_id}".strip()

    # ---------------------------------------------------------
    # Validation
    # ---------------------------------------------------------

    async def validate_project(self, project_id: str):
        chunks = await self.chunk_repository.get_chunks(project_id)
        if not chunks:
            return None
        return {"project_id": project_id}

    # ---------------------------------------------------------
    # Indexing
    # ---------------------------------------------------------

    async def index_project(self, project_id: str, do_reset: bool = False):

        collection_name = self.create_collection_name(project_id)
        chunks = await self.chunk_repository.get_chunks(project_id)

        if not chunks:
            return 0

        self.vectordb_client.create_collection(
            collection_name=collection_name,
            embedding_size=self.embedding_client.embedding_size,
            do_reset=do_reset
        )

        texts = [c.text for c in chunks]

        embeddings = [
            self.embedding_client.embed_text(
                text=t,
                document_type=DocumentTypeEnum.DOCUMENT.value
            )
            for t in texts
        ]

        record_ids = [c.chunk_id for c in chunks]

        success = self.vectordb_client.insert_many(
            collection_name=collection_name,
            texts=texts,
            vectors=embeddings,
            metadata=[c.metadata for c in chunks],
            record_ids=record_ids
        )

        if not success:
            return 0

        return len(chunks)

    # ---------------------------------------------------------
    # Search
    # ---------------------------------------------------------

    def search(self, project_id: str, query: str, limit: int = 5):

        collection_name = self.create_collection_name(project_id)

        query_vector = self.embedding_client.embed_text(
            text=query,
            document_type=DocumentTypeEnum.QUERY.value
        )

        if not query_vector:
            return []

        search_results = self.vectordb_client.search_by_vector(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=limit
        )

        if not search_results:
            return []

        return json.loads(
            json.dumps(search_results, default=lambda x: x.__dict__)
        )

    # ---------------------------------------------------------
    # Collection Info
    # ---------------------------------------------------------

    def get_vector_db_collection_info(self, project_id: str):
        collection_name = self.create_collection_name(project_id)
        collection_info = self.vectordb_client.get_collection_info(
            collection_name=collection_name
        )
        return json.loads(
            json.dumps(collection_info, default=lambda x: x.__dict__)
        )

    # ---------------------------------------------------------
    # RAG - Generate Augmented Answer
    # ---------------------------------------------------------

    def generate_augmented_answer(self, project_id: str, question: str,
                                   limit: int = 5, score_threshold: float = 0.4):

        collection_name = self.create_collection_name(project_id)

        # Step 1: Embed the query
        query_vector = self.embedding_client.embed_text(
            text=question,
            document_type=DocumentTypeEnum.QUERY.value
        )
        if not query_vector:
            return {"error": "Query embedding failed"}

        # Step 2: Search vector DB
        search_results = self.vectordb_client.search_by_vector(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=limit
        )
        if not search_results:
            return {"error": "No relevant documents found"}

        # Step 3: Filter by similarity score threshold
        # WHY: chunks below threshold are nearly irrelevant and cause hallucination
        filtered_results = [r for r in search_results if r["score"] >= score_threshold]

        if not filtered_results:
            return {
                "query": question,
                "answer": "I could not find relevant information in the uploaded materials to answer this question.",
                "sources": [],
                "scores": [],
                "num_sources": 0
            }

        # Step 4: Build numbered context so LLM can cite sources
        context_parts = []
        for i, result in enumerate(filtered_results, 1):
            text = result["payload"].get("text", "")
            score = result["score"]
            context_parts.append(f"[Source {i}] (relevance: {score:.2f})\n{text}")

        context = "\n\n".join(context_parts)

        # Step 5: System prompt - the "contract" for the LLM
        system_prompt = """You are an expert engineering tutor helping university students.
Your answers must be based STRICTLY on the context provided below.
Rules you must follow:
1. If the answer is clearly in the context, answer it step by step.
2. If the context is partially relevant, use what is available and say what is missing.
3. If the context does not contain the answer, say exactly: "This topic is not covered in the uploaded materials."
4. Never invent facts, formulas, or explanations not present in the context.
5. When possible, refer to which source your answer comes from (e.g. "According to Source 1...")."""

        # Step 6: User message with context and question
        user_prompt = f"""Context from uploaded study materials:

{context}

Student question: {question}

Answer:"""

        # Step 7: Generate answer
        answer = self.generation_client.generate_text(
            prompt=user_prompt,
            chat_history=[
                {"role": "system", "content": system_prompt}
            ]
        )

        return {
            "query": question,
            "answer": answer,
            "sources": [r["payload"].get("text", "") for r in filtered_results],
            "scores": [r["score"] for r in filtered_results],
            "num_sources": len(filtered_results)
        }