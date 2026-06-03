#!/usr/bin/env python3
"""
Standalone ablation study runner — no HTTP server needed.
Runs directly against the vector DB and Gemini API.

Usage (from src/):
    python run_ablation.py
"""
import os, sys, json, asyncio, logging, time

os.environ["TOKENIZERS_PARALLELISM"] = "false"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("ablation")

# ── 0. Load settings & clients ─────────────────────────────────────────────
from helpers.config import get_settings
from stores.LLM.LLMProviderFactory import LLMProviderFactory
from stores.LLM.LLMEnums import LLMBackendEnum
from stores.vectordb.VectorDBProviderFactory import VectorDBProviderFactory
from stores.bm25.BM25ProviderFactory import BM25ProviderFactory
from repositories.json_chunk_repository import JsonChunkRepository
from controllers import NLPController
from evaluation.ragas_evaluator import RAGASEvaluator
from evaluation.test_set import get_test_cases

settings = get_settings()

# Generation client (Gemini)
llm_factory = LLMProviderFactory(config=settings)
generation_client = llm_factory.create(settings.GENERATION_BACKEND)
if settings.GENERATION_BACKEND == LLMBackendEnum.GEMINI.value:
    gemini_model = getattr(settings, "GEMINI_MODEL_ID", None) or "gemini-2.5-flash"
    generation_client.set_generation_model(model_id=gemini_model)
    logger.info(f"Generation: Gemini {gemini_model}")
elif settings.GENERATION_BACKEND == LLMBackendEnum.GROQ.value:
    generation_client.set_generation_model(model_id=settings.GENERATION_MODEL_ID)
    logger.info(f"Generation: Groq {settings.GENERATION_MODEL_ID}")

# Embedding client (local HuggingFace)
embedding_client = llm_factory.create(LLMBackendEnum.LOCAL.value)
embedding_client.set_embedding_model(
    model_id=settings.EMBEDDING_MODEL_ID,
    embedding_size=settings.EMBEDDING_MODEL_SIZE,
)
logger.info(f"Embedding: {settings.EMBEDDING_MODEL_ID}")

# Vector DB
vectordb_factory = VectorDBProviderFactory(config=settings)
vectordb_client = vectordb_factory.create(provider=settings.VECTOR_DB_BACKEND)
vectordb_client.connect()
logger.info(f"VectorDB: {settings.VECTOR_DB_BACKEND} @ {settings.VECTOR_DB_PATH}")

# BM25
bm25_factory = BM25ProviderFactory(config=settings)
bm25_client = bm25_factory.create(provider=settings.BM25_BACKEND)
logger.info(f"BM25: {settings.BM25_BACKEND}")

# Chunk repository
chunk_repository = JsonChunkRepository(storage_path="chunk_staging_buffer.json")

# Contextual cache
from services.contextual_cache import ContextualDescriptionCache
contextual_cache = ContextualDescriptionCache(storage_path="contextual_cache.json")

# NLP controller
controller = NLPController(
    vectordb_client=vectordb_client,
    generation_client=generation_client,
    embedding_client=embedding_client,
    chunk_repository=chunk_repository,
    reranker_client=None,
    bm25_client=bm25_client,
    contextual_cache=contextual_cache,
)

# ── 1. Target project ──────────────────────────────────────────────────────
PROJECT_ID = "p_4au76z3ixcdc"          # your Algorithms book project

# ── 2. Test cases ──────────────────────────────────────────────────────────
cases = get_test_cases(dataset="scientific")
logger.info(f"Test set: {len(cases)} cases")

# ── 3. Ablation configs ────────────────────────────────────────────────────
ABLATION_RUNS = [
    {
        "name":               "baseline",
        "enable_multi_query": False,
        "enable_hybrid":      False,
        "enable_reranker":    False,
        "enable_compression": False,
    },
    {
        "name":               "+hybrid",
        "enable_multi_query": False,
        "enable_hybrid":      True,
        "enable_reranker":    False,
        "enable_compression": False,
    },
    {
        "name":               "+reranker",
        "enable_multi_query": False,
        "enable_hybrid":      True,
        "enable_reranker":    True,
        "enable_compression": False,
    },
    {
        "name":               "+compression",
        "enable_multi_query": False,
        "enable_hybrid":      True,
        "enable_reranker":    True,
        "enable_compression": True,
    },
]

# ── 4. Helpers ─────────────────────────────────────────────────────────────

def run_batch(cases, *, enable_multi_query, enable_hybrid,
              enable_reranker, enable_compression):
    from routes._nlp_handlers import _run_rag
    test_cases, test_details = [], []
    for case in cases:
        try:
            rag = _run_rag(
                controller=controller,
                project_id=PROJECT_ID,
                question=case["question"],
                limit=5,
                intent="rag_only",
                enable_multi_query=enable_multi_query,
                enable_hybrid=enable_hybrid,
                enable_reranker=enable_reranker,
                enable_compression=enable_compression,
            )
            sources = rag.get("sources", [])
            if isinstance(sources, str):
                sources = [sources]
            answer = rag.get("answer", "")
            logger.info(f"  Q: {case['question'][:60]!r}")
            logger.info(f"  A: {answer[:120]!r}")
            test_cases.append({
                "question": case["question"],
                "answer": answer,
                "contexts": sources,
                "ground_truth": case["ground_truth"],
            })
            test_details.append({
                "question": case["question"],
                "level": case.get("level"),
                "answer": answer[:200],
                "num_contexts": len(sources),
                "timings": rag.get("timings", {}),
                "compression_ratios": rag.get("compression_ratios", []),
            })
        except Exception as e:
            logger.error(f"RAG failed for '{case['question']}': {e}")
    return test_cases, test_details


async def evaluate_and_save(run_name, test_cases, test_details, dataset="scientific"):
    label = f"ablation_{dataset}_{run_name.replace(' ', '_')}"
    logger.info(f"\n{'='*60}\nEvaluating: {label}\n{'='*60}")
    evaluator = RAGASEvaluator(timeout=900)
    scores = await evaluator.evaluate(test_cases)
    logger.info(f"Scores → {scores}")
    evaluator.save_results(scores, test_details=test_details, label=label,
                           output_path="evaluation_results.json")
    return scores


async def main():
    all_scores = {}

    for run in ABLATION_RUNS:
        rname = run["name"]
        logger.info(f"\n{'#'*60}\nRAG batch: {rname}\n{'#'*60}")

        t0 = time.time()
        test_cases, test_details = run_batch(
            cases,
            enable_multi_query=run["enable_multi_query"],
            enable_hybrid=run["enable_hybrid"],
            enable_reranker=run["enable_reranker"],
            enable_compression=run["enable_compression"],
        )
        batch_ms = round((time.time() - t0) * 1000)
        logger.info(f"Batch done in {batch_ms}ms — {len(test_cases)} test cases built")

        scores = await evaluate_and_save(rname, test_cases, test_details)
        all_scores[rname] = scores

    logger.info("\n\n" + "="*60)
    logger.info("ABLATION COMPLETE — Final scores:")
    logger.info("="*60)
    header = f"{'Config':<25}  {'Faith':>6}  {'Relev':>6}  {'Prec':>6}  {'Recall':>6}  {'Overall':>7}"
    logger.info(header)
    for rname, sc in all_scores.items():
        row = (
            f"{rname:<25}  "
            f"{sc.get('Faithfulness', 0):.3f}  "
            f"{sc.get('AnswerRelevancy', 0):.3f}  "
            f"{sc.get('ContextPrecision', 0):.3f}  "
            f"{sc.get('ContextRecall', 0):.3f}  "
            f"{sc.get('overall', 0):.3f}"
        )
        logger.info(row)

    vectordb_client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
