#!/usr/bin/env python3
"""
Mixed-corpus ingest for the ablation study
==========================================

Builds ONE large collection (`rag_mixed`, plus contextual variant
`rag_mixed_ctx`) from several Supabase documents so retrieval is genuinely
hard: a Networks question's ~5 relevant chunks must be found among ~550 chunks
of OS / algorithms / database distractors. THIS is the regime where
RAG-Fusion / hybrid / reranking demonstrably beat plain dense search (small
single-doc corpora give baseline ~1.0 recall, leaving no headroom).

Chunk IDs are made globally unique across the combined files (each Supabase
file numbers its chunks from 0, which would otherwise overwrite each other in
the single combined collection / BM25 index).

Run from src/ AFTER any other ablation run has finished (local Qdrant is
single-process):
    PYTHONPATH=. .venv/bin/python ablation/ab_ingest_mixed.py
"""
import os, sys, asyncio, logging

os.environ["TOKENIZERS_PARALLELISM"] = "false"
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ab_ingest_mixed")

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SRC)

import psycopg
from helpers.config import get_settings
from models.chunk import Chunk as RAGChunk
from ablation.ab_ingest import _load_db_url   # reuse DB-url loader

MIXED_PID = "rag_mixed"

# file_id -> short label. First two are the ANSWER-bearing docs (the test
# questions are about them); the rest are distractors of varying closeness.
FILES = [
    ("b510a5f8-d8f3-4ca1-92bf-bc0750a275b8", "networks (answers)"),
    ("ae02f2ed-d5cc-4d17-99fe-b4ecd9113c67", "os_threads (answers)"),
    ("fab96441-df51-4284-8399-524cc757700b", "os_syscalls (near distractor)"),
    ("5ed89bc1-35d0-423e-8511-4cd38178c458", "os_scheduling (near distractor)"),
    ("7a1552ce-6562-499d-b2ad-0597d6cfd801", "greedy_algorithms (far distractor)"),
    ("085222c6-ef3d-4d0e-8dd5-4f0a5cead761", "db_paper (far distractor)"),
]


def fetch_all(cur) -> list:
    """Fetch every file's chunks into one list with globally-unique chunk_id."""
    chunks, gid = [], 0
    for file_id, label in FILES:
        cur.execute("SELECT file_name, source_type, title FROM uploaded_files WHERE id=%s",
                    (file_id,))
        row = cur.fetchone()
        if not row:
            log.warning(f"file {file_id} ({label}) not found — skipping"); continue
        file_name, source_type, title = row
        doc_title = title or file_name
        cur.execute(
            """SELECT s.heading, s.page, c.content, c.chunk_type, c.chunk_metadata
               FROM sections s JOIN chunks c ON c.section_id = s.id
               WHERE s.file_id = %s ORDER BY s.section_index, c.chunk_index""",
            (file_id,))
        n = 0
        for heading, page, content, chunk_type, chunk_meta in cur.fetchall():
            content = (content or "").strip()
            if not content:
                continue
            chunk_meta = chunk_meta or {}
            meta = {
                "source": file_name, "source_type": source_type or "pdf",
                "doc_title": doc_title,
                "page": page if page is not None else chunk_meta.get("page"),
                "section_heading": heading or chunk_meta.get("section_heading"),
                "chunk_type": chunk_type or chunk_meta.get("chunk_type", "text"),
                "project_id": MIXED_PID, "file_id": file_id, "doc_label": label,
            }
            if chunk_meta.get("image_path"):
                meta["image_path"] = chunk_meta["image_path"]
            chunks.append(RAGChunk(chunk_id=gid, text=content, metadata=meta))
            gid += 1; n += 1
        log.info(f"  {label:34s} {file_id}: +{n} chunks (running total {gid})")
    return chunks


async def main():
    build_ctx = "--with-ctx" in sys.argv
    settings = get_settings()

    from stores.LLM.LLMProviderFactory import LLMProviderFactory
    from stores.LLM.LLMEnums import LLMBackendEnum
    from stores.vectordb.VectorDBProviderFactory import VectorDBProviderFactory
    from stores.bm25.BM25ProviderFactory import BM25ProviderFactory
    from repositories.json_chunk_repository import JsonChunkRepository
    from services.contextual_cache import ContextualDescriptionCache
    from controllers import NLPController

    llm_factory = LLMProviderFactory(config=settings)
    gen = llm_factory.create(settings.GENERATION_BACKEND)
    if settings.GENERATION_BACKEND == LLMBackendEnum.OPENAI_COMPAT.value:
        gen.set_generation_model(getattr(settings, "OPENAI_COMPAT_MODEL", "gpt-oss-120b"))
    elif settings.GENERATION_BACKEND == LLMBackendEnum.GEMINI.value:
        gen.set_generation_model(getattr(settings, "GEMINI_MODEL_ID", "gemini-2.5-flash"))
    else:
        gen.set_generation_model(settings.GENERATION_MODEL_ID)
    emb = llm_factory.create(LLMBackendEnum.LOCAL.value)
    emb.set_embedding_model(model_id=settings.EMBEDDING_MODEL_ID,
                            embedding_size=settings.EMBEDDING_MODEL_SIZE)
    vdb = VectorDBProviderFactory(config=settings).create(provider=settings.VECTOR_DB_BACKEND)
    vdb.connect()
    bm25 = BM25ProviderFactory(config=settings).create(provider=settings.BM25_BACKEND)
    repo = JsonChunkRepository(storage_path="chunk_staging_buffer.json")
    cache = ContextualDescriptionCache(storage_path="contextual_cache.json")
    controller = NLPController(vectordb_client=vdb, generation_client=gen,
                               embedding_client=emb, chunk_repository=repo,
                               reranker_client=None, bm25_client=bm25,
                               contextual_cache=cache)

    db_url = _load_db_url()
    with psycopg.connect(db_url, connect_timeout=30) as conn, conn.cursor() as cur:
        chunks = fetch_all(cur)
    log.info(f"TOTAL mixed-corpus chunks: {len(chunks)}")

    # Stage under rag_mixed (+ ctx variant). Reset first so re-runs are clean.
    await repo.delete_project_chunks(MIXED_PID)
    await repo.add_chunks(MIXED_PID, chunks)
    if build_ctx:
        await repo.delete_project_chunks(MIXED_PID + "_ctx")
        ctx_chunks = [RAGChunk(chunk_id=c.chunk_id, text=c.text,
                               metadata={**c.metadata, "project_id": MIXED_PID + "_ctx"})
                      for c in chunks]
        await repo.add_chunks(MIXED_PID + "_ctx", ctx_chunks)

    controller.app_settings.CONTEXTUAL_RETRIEVAL_ENABLED = False
    n = await controller.index_project(project_id=MIXED_PID, do_reset=True)
    log.info(f"Indexed {MIXED_PID}: {n} chunks (contextual OFF)")

    if build_ctx:
        controller.app_settings.CONTEXTUAL_RETRIEVAL_ENABLED = True
        n = await controller.index_project(project_id=MIXED_PID + "_ctx", do_reset=True)
        log.info(f"Indexed {MIXED_PID}_ctx: {n} chunks (contextual ON)")

    vdb.disconnect()
    log.info("MIXED INGEST COMPLETE." + ("" if build_ctx else
             "  (ctx variant skipped — pass --with-ctx to also build rag_mixed_ctx)"))


if __name__ == "__main__":
    asyncio.run(main())
