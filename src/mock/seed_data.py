from models.chunk import Chunk


async def seed_project(repository):

    demo_chunks = [
        Chunk(
            chunk_id=1,
            text="Qdrant is a high-performance vector database.",
            metadata={"source": "doc1"}
        ),
        Chunk(
            chunk_id=2,
            text="Semantic search uses embeddings to compare meaning.",
            metadata={"source": "doc2"}
        ),
        Chunk(
            chunk_id=3,
            text="RAG combines retrieval with generation.",
            metadata={"source": "doc3"}
        )
    ]

    await repository.add_chunks("demo_project", demo_chunks)