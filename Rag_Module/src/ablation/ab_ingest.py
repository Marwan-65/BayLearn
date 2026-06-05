#!/usr/bin/env python3
"""
Ablation ingest + index
========================

Starts the RAG stores clean, pulls the two evaluation documents' chunks
directly from the shared Supabase Postgres DB (the same chunks the Input
Parsing Module serves over HTTP — replicated here so the parsing service does
not have to be running), and builds FOUR Qdrant + BM25 collections:

    rag_net      / rag_os        -> Contextual Retrieval OFF  (baseline index)
    rag_net_ctx  / rag_os_ctx    -> Contextual Retrieval ON   (Anthropic 2024)

The two ctx-on/off pairs let the ablation measure the index-time Contextual
Retrieval layer (which cannot be toggled at query time) by retrieving against
each collection with the same query-time config.

Run from src/:  PYTHONPATH=. .venv/bin/python ablation/ab_ingest.py
"""
import os, sys, json, shutil, asyncio, logging, datetime

os.environ["TOKENIZERS_PARALLELISM"] = "false"
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ab_ingest")

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SRC)

import psycopg
from helpers.config import get_settings
from models.chunk import Chunk as RAGChunk

# ── Targets: file_id in Supabase -> (project_id base, human label) ───────────
TARGETS = {
    "b510a5f8-d8f3-4ca1-92bf-bc0750a275b8": ("rag_net", "Computer Networks (transport)"),
    "ae02f2ed-d5cc-4d17-99fe-b4ecd9113c67": ("rag_os",  "OS Concepts (Threads Ch.4)"),
}

# Pull the DB URL from the Input Parsing Module's .env (single source of truth).
def _load_db_url() -> str:
    ip_env = os.path.join(SRC, "..", "..", "Input-Parsing-Module", ".env")
    url = os.getenv("DATABASE_URL")
    if not url and os.path.exists(ip_env):
        for line in open(ip_env):
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                url = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    if not url:
        raise SystemExit("DATABASE_URL not found (env or Input-Parsing-Module/.env)")
    return url


def fetch_chunks_for_file(cur, file_id: str, project_id: str) -> list:
    """Replicate InputParsingAdapter.fetch_chunks_from_db against Postgres."""
    cur.execute(
        "SELECT file_name, source_type, title FROM uploaded_files WHERE id=%s",
        (file_id,),
    )
    row = cur.fetchone()
    if not row:
        raise SystemExit(f"file_id {file_id} not found in DB")
    file_name, source_type, title = row
    doc_title = title or file_name

    # sections joined to chunks, ordered the way the parsing module emits them.
    cur.execute(
        """
        SELECT s.heading, s.page, c.content, c.chunk_type, c.chunk_metadata, c.id
        FROM sections s JOIN chunks c ON c.section_id = s.id
        WHERE s.file_id = %s
        ORDER BY s.section_index, c.chunk_index
        """,
        (file_id,),
    )
    rag_chunks = []
    counter = 0
    for heading, page, content, chunk_type, chunk_meta, parsing_chunk_id in cur.fetchall():
        content = (content or "").strip()
        if not content:
            continue
        chunk_meta = chunk_meta or {}
        meta = {
            "source": file_name,
            "source_type": source_type or "pdf",
            "doc_title": doc_title,
            "page": page if page is not None else chunk_meta.get("page"),
            "section_heading": heading or chunk_meta.get("section_heading"),
            "chunk_type": chunk_type or chunk_meta.get("chunk_type", "text"),
            "project_id": project_id,
            "file_id": file_id,
            "parsing_chunk_id": str(parsing_chunk_id),
        }
        if chunk_meta.get("image_path"):
            meta["image_path"] = chunk_meta["image_path"]
        rag_chunks.append(RAGChunk(chunk_id=counter, text=content, metadata=meta))
        counter += 1
    log.info(f"{project_id}: fetched {len(rag_chunks)} chunks (doc='{doc_title}')")
    return rag_chunks


def backup_and_wipe():
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bdir = os.path.join(SRC, f"_ablation_backup_{stamp}")
    os.makedirs(bdir, exist_ok=True)
    log.info(f"Backing up current stores -> {bdir}")
    for name in ["chunk_staging_buffer.json", "chunks_storage.json",
                 "contextual_cache.json", "evaluation_results.json"]:
        p = os.path.join(SRC, name)
        if os.path.exists(p):
            shutil.copy2(p, os.path.join(bdir, name))
    for d in ["vector_db", "bm25_db"]:
        p = os.path.join(SRC, d)
        if os.path.exists(p):
            shutil.move(p, os.path.join(bdir, d))
    # Start clean (keep extracted_images/ — images are used in chat).
    for name in ["chunk_staging_buffer.json", "chunks_storage.json",
                 "contextual_cache.json"]:
        with open(os.path.join(SRC, name), "w") as f:
            f.write("{}")
    os.makedirs(os.path.join(SRC, "bm25_db"), exist_ok=True)
    log.info("Stores wiped clean (extracted_images/ kept).")
    return bdir


async def main():
    settings = get_settings()
    backup_and_wipe()

    # ── Build clients ────────────────────────────────────────────────────
    from stores.LLM.LLMProviderFactory import LLMProviderFactory
    from stores.LLM.LLMEnums import LLMBackendEnum
    from stores.vectordb.VectorDBProviderFactory import VectorDBProviderFactory
    from stores.bm25.BM25ProviderFactory import BM25ProviderFactory
    from repositories.json_chunk_repository import JsonChunkRepository
    from services.contextual_cache import ContextualDescriptionCache
    from controllers import NLPController

    llm_factory = LLMProviderFactory(config=settings)
    generation_client = llm_factory.create(settings.GENERATION_BACKEND)
    generation_client.set_generation_model(model_id=settings.GENERATION_MODEL_ID)
    embedding_client = llm_factory.create(LLMBackendEnum.LOCAL.value)
    embedding_client.set_embedding_model(
        model_id=settings.EMBEDDING_MODEL_ID,
        embedding_size=settings.EMBEDDING_MODEL_SIZE,
    )
    vectordb_factory = VectorDBProviderFactory(config=settings)
    vectordb_client = vectordb_factory.create(provider=settings.VECTOR_DB_BACKEND)
    vectordb_client.connect()
    bm25_client = BM25ProviderFactory(config=settings).create(provider=settings.BM25_BACKEND)
    chunk_repository = JsonChunkRepository(storage_path="chunk_staging_buffer.json")
    contextual_cache = ContextualDescriptionCache(storage_path="contextual_cache.json")

    controller = NLPController(
        vectordb_client=vectordb_client,
        generation_client=generation_client,
        embedding_client=embedding_client,
        chunk_repository=chunk_repository,
        reranker_client=None,           # not needed for indexing
        bm25_client=bm25_client,
        contextual_cache=contextual_cache,
    )

    # ── Pull chunks from Supabase and stage under all 4 project_ids ──────
    db_url = _load_db_url()
    staged = {}   # base project_id -> chunks
    with psycopg.connect(db_url, connect_timeout=30) as conn:
        with conn.cursor() as cur:
            for file_id, (base_pid, label) in TARGETS.items():
                chunks = fetch_chunks_for_file(cur, file_id, base_pid)
                staged[base_pid] = chunks

    for base_pid, chunks in staged.items():
        await chunk_repository.add_chunks(base_pid, chunks)
        # ctx variant shares the same chunks under a parallel project id
        ctx_chunks = [RAGChunk(chunk_id=c.chunk_id, text=c.text,
                               metadata={**c.metadata, "project_id": f"{base_pid}_ctx"})
                      for c in chunks]
        await chunk_repository.add_chunks(f"{base_pid}_ctx", ctx_chunks)

    # ── Index: ctx OFF first, then ctx ON ───────────────────────────────
    for ctx_on in (False, True):
        controller.app_settings.CONTEXTUAL_RETRIEVAL_ENABLED = ctx_on
        for base_pid in staged:
            pid = f"{base_pid}_ctx" if ctx_on else base_pid
            n = await controller.index_project(project_id=pid, do_reset=True)
            log.info(f"Indexed {pid}: {n} chunks  (contextual_retrieval={ctx_on})")

    vectordb_client.disconnect()
    log.info("INGEST COMPLETE. Collections: "
             "rag_net, rag_os (ctx off) + rag_net_ctx, rag_os_ctx (ctx on)")


if __name__ == "__main__":
    asyncio.run(main())
