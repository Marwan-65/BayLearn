import json
from typing import List
from stores.LLM.LLMEnum import DocumentTypeEnum
from .base import BaseController


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

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------

    def create_collection_name(self, project_id: str):
        return f"collection_{project_id}".strip()

    # ---------------------------------------------------------
    # Validation
    # ---------------------------------------------------------

    async def validate_project(self, project_id: str):
        """
        If project has chunks in repository, it exists.
        """
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

        if do_reset:
            self.vectordb_client.delete_collection(
                collection_name=collection_name
            )

        texts = [c.text for c in chunks]

        embeddings = self.embedding_client.embed_text(
            text=texts,
            document_type=DocumentTypeEnum.DOCUMENT.value
        )

        payloads = [
            {"text": c.text, **c.metadata}
            for c in chunks
        ]

        record_ids = [c.chunk_id for c in chunks]

        self.vectordb_client.insert_many(
            collection_name=collection_name,
            vectors=embeddings,
            payloads=payloads,
            record_ids=record_ids
        )

        return len(chunks)

    # ---------------------------------------------------------
    # Search
    # ---------------------------------------------------------

    def search(self, project_id: str, query: str, top_k: int = 5):

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
            limit=top_k
        )

        if not search_results:
            return []

        return json.loads(
            json.dumps(
                search_results,
                default=lambda x: x.__dict__
            )
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
            json.dumps(
                collection_info,
                default=lambda x: x.__dict__
            )
        )
        

    def generate_augmented_answer(self, project_id: str, question: str, top_k: int = 5):
        collection_name = self.create_collection_name(project_id)

        # 1️⃣ Embed query
        query_vector = self.embedding_client.embed_text(
            text=question,
            document_type=DocumentTypeEnum.QUERY.value
        )

        if not query_vector:
            return {"error": "Query embedding failed"}

        # 2️⃣ Search vector DB
        search_results = self.vectordb_client.search_by_vector(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=top_k
        )

        if not search_results:
            return {"error": "No relevant documents found"}

        # 3️⃣ Extract retrieved texts
        retrieved_chunks = [
            result.payload.get("text", "")
            for result in search_results
        ]

        # 4️⃣ Construct RAG context
        context = "\n\n".join(retrieved_chunks)

        augmented_prompt = f"""
    You are a helpful AI assistant.

    Use ONLY the following context to answer the question.
    If the answer is not in the context, say you don't know.

    Context:
    {context}

    Question:
    {question}

    Answer:
    """

        # Generate answer
        answer = self.generation_client.generate_text(
            prompt=augmented_prompt
        )

        return {
            "query": question,
            "answer": answer,
            "sources": retrieved_chunks
        }