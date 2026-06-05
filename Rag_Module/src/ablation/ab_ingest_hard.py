#!/usr/bin/env python3
"""
HARD-corpus ingest for the ablation (collection `rag_hard`).
============================================================
Builds a genuinely difficult retrieval corpus so the improvement layers
(RAG-Fusion / hybrid / reranker) can actually beat baseline on RETRIEVAL, not
just generation. The answer-bearing networking transport chapter (~15 chunks)
is hidden inside a ~9,000-chunk haystack dominated by the full Operating
Systems textbook — which shares vocabulary with networking transport
(timeout, window, queue, buffer, scheduling, process) and so produces real
NEAR-collisions, not the trivially-separable far distractors of `rag_mixed`.

Run from src/:
    PYTHONPATH=. .venv/bin/python ablation/ab_ingest_hard.py
"""
import os, sys, asyncio, logging
os.environ["TOKENIZERS_PARALLELISM"] = "false"
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ab_ingest_hard")
SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SRC)

import psycopg
from helpers.config import get_settings
from models.chunk import Chunk as RAGChunk
from ablation.ab_ingest import _load_db_url

HARD_PID = "rag_os_hard"

# Focused OS-threads hard corpus. First file is the ONLY answer source (the
# Threads chapter). Scheduling + System-Calls are SAME-DOMAIN near-distractors
# (heavy vocab overlap: process, thread, context switch, kernel, CPU) — this is
# where dense search confuses related OS concepts and reranking/hybrid/fusion
# earn their value. Algorithms are far-distractors for variety. ~420 chunks.
# (short id prefixes; resolved to full UUIDs at fetch time)
FILES = [
    ("ae02f2ed", "os_threads (answers)"),
    ("5ed89bc1", "os_scheduling (NEAR distractor)"),
    ("fab96441", "os_syscalls (NEAR distractor)"),
    ("7a1552ce", "greedy_algorithms (far distractor)"),
    ("003f0302", "dynamic_programming (far distractor)"),
]


def fetch_all(cur) -> list:
    chunks, gid = [], 0
    for prefix, label in FILES:
        cur.execute("SELECT id, file_name, source_type, title FROM uploaded_files WHERE id::text LIKE %s",
                    (prefix + "%",))
        row0 = cur.fetchone()
        if not row0:
            log.warning(f"file {prefix} ({label}) not found — skipping"); continue
        file_id = str(row0[0])
        row = row0[1:]
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
                "project_id": HARD_PID, "file_id": file_id, "doc_label": label,
            }
            chunks.append(RAGChunk(chunk_id=gid, text=content, metadata=meta))
            gid += 1; n += 1
        log.info(f"  {label:42s} +{n} chunks (running total {gid})")
    return chunks


async def main():
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
    if settings.GENERATION_BACKEND == LLMBackendEnum.GEMINI.value:
        gen.set_generation_model(getattr(settings, "GEMINI_MODEL_ID", "gemini-2.5-flash-lite"))
    elif settings.GENERATION_BACKEND == LLMBackendEnum.OPENAI_COMPAT.value:
        gen.set_generation_model(getattr(settings, "OPENAI_COMPAT_MODEL", "gpt-oss-120b"))
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
    log.info(f"TOTAL hard-corpus chunks: {len(chunks)}")

    await repo.delete_project_chunks(HARD_PID)
    await repo.add_chunks(HARD_PID, chunks)
    controller.app_settings.CONTEXTUAL_RETRIEVAL_ENABLED = False
    n = await controller.index_project(project_id=HARD_PID, chunks=chunks, do_reset=True)
    log.info(f"Indexed {HARD_PID}: {n} chunks (contextual OFF)")
    vdb.disconnect()
    log.info("HARD INGEST COMPLETE.")


if __name__ == "__main__":
    asyncio.run(main())
