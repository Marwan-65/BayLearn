#!/usr/bin/env python3
"""
Ablation study runner (Gemini-backed)
======================================

Runs the layered RAG ablation on the two evaluation documents and scores each
configuration with RAGAS (faithfulness, answer relevancy, context precision,
context recall). Designed for Gemini Flash as the generation + judge LLM
(Groq free-tier tokens are exhausted) — it simply uses whatever
GENERATION_BACKEND / GEMINI_API_KEY the .env specifies, and RAGASEvaluator
auto-selects Gemini when GEMINI_API_KEY is set.

Layer ladder (each row adds one technique to the previous):
    baseline      -> dense vector search only
    +hyde         -> Hypothetical Document Embeddings (Gao et al. 2022)
    +rag_fusion   -> multi-query expansion + RRF (replaces HyDE in production)
    +hybrid       -> add BM25 sparse + RRF fusion
    +reranker     -> add cross-encoder reranking
    +compression  -> add contextual compression  (== full query-time pipeline)
    +contextual   -> full pipeline, but retrieving from the contextual-retrieval
                     index (Anthropic 2024) instead of the plain index.

Results are appended incrementally to ablation_results.json and the run is
resumable: a (dataset, config) pair already present is skipped.

Run from src/:  PYTHONPATH=. .venv/bin/python ablation/ab_run.py
"""
import os, sys, json, time, asyncio, logging

os.environ["TOKENIZERS_PARALLELISM"] = "false"
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ab_run")

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SRC)

from helpers.config import get_settings
from stores.LLM.LLMProviderFactory import LLMProviderFactory
from stores.LLM.LLMEnums import LLMBackendEnum
from stores.vectordb.VectorDBProviderFactory import VectorDBProviderFactory
from stores.bm25.BM25ProviderFactory import BM25ProviderFactory
from repositories.json_chunk_repository import JsonChunkRepository
from services.contextual_cache import ContextualDescriptionCache
from controllers import NLPController
from evaluation.ragas_evaluator import RAGASEvaluator
from evaluation.test_set import get_test_cases
from routes._nlp_handlers import _run_batch, _avg_latency

RESULTS_PATH = "ablation_results.json"
INTER_Q_SLEEP = float(os.getenv("AB_SLEEP", "1.0"))   # gentle pacing for RPM caps

# ── Datasets: (test-set name, base collection [ctx off], ctx collection) ─────
DATASETS = [
    ("networks",   "rag_net", "rag_net_ctx"),
    ("os_threads", "rag_os",  "rag_os_ctx"),
]

# Ablation design (flags: mq=multi-query/RAG-Fusion, hy=hybrid BM25+RRF,
# rr=cross-encoder rerank, cp=contextual compression, hd=HyDE):
#
#   baseline                 dense vector search only
#   ── two PARALLEL query-expansion branches over baseline (NOT cumulative) ──
#   baseline+hyde            HyDE alone        (the technique we REPLACED)
#   rag_fusion               RAG-Fusion alone  (the technique we KEPT)
#   ── cumulative ladder, built on the winner (RAG-Fusion) ──
#   +hybrid                  RAG-Fusion + BM25/RRF
#   +reranker                + cross-encoder rerank
#   +compression             + contextual compression  (= full query-time pipeline)
#   +contextual              full pipeline on the contextual-retrieval index
#
# HyDE and RAG-Fusion are alternatives (HyDE was dropped in favour of RAG-Fusion),
# so they are compared side-by-side against baseline — never stacked together.
LADDER = [
    ("baseline",        dict(mq=False, hy=False, rr=False, cp=False, hd=False), "base"),
    ("baseline+hyde",   dict(mq=False, hy=False, rr=False, cp=False, hd=True),  "base"),
    ("rag_fusion",      dict(mq=True,  hy=False, rr=False, cp=False, hd=False), "base"),
    ("+hybrid",         dict(mq=True,  hy=True,  rr=False, cp=False, hd=False), "base"),
    ("+reranker",       dict(mq=True,  hy=True,  rr=True,  cp=False, hd=False), "base"),
    ("+compression",    dict(mq=True,  hy=True,  rr=True,  cp=True,  hd=False), "base"),
    ("+contextual",     dict(mq=True,  hy=True,  rr=True,  cp=True,  hd=False), "ctx"),
]


def load_results() -> dict:
    if os.path.exists(RESULTS_PATH):
        try:
            return json.load(open(RESULTS_PATH))
        except Exception:
            return {}
    return {}


def save_results(data: dict):
    with open(RESULTS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def build_controller(settings):
    llm_factory = LLMProviderFactory(config=settings)
    gen = llm_factory.create(settings.GENERATION_BACKEND)
    if settings.GENERATION_BACKEND == LLMBackendEnum.GEMINI.value:
        gen.set_generation_model(model_id=getattr(settings, "GEMINI_MODEL_ID", "gemini-2.5-flash"))
        log.info(f"Generation: Gemini {getattr(settings,'GEMINI_MODEL_ID','gemini-2.5-flash')}")
    elif settings.GENERATION_BACKEND == LLMBackendEnum.OPENAI_COMPAT.value:
        m = getattr(settings, "OPENAI_COMPAT_MODEL", "llama-3.3-70b")
        gen.set_generation_model(model_id=m)
        log.info(f"Generation: OpenAI-compat {m} @ {getattr(settings,'OPENAI_COMPAT_BASE_URL','')}")
    else:
        gen.set_generation_model(model_id=settings.GENERATION_MODEL_ID)
        log.info(f"Generation: {settings.GENERATION_BACKEND} {settings.GENERATION_MODEL_ID}")

    emb = llm_factory.create(LLMBackendEnum.LOCAL.value)
    emb.set_embedding_model(model_id=settings.EMBEDDING_MODEL_ID,
                            embedding_size=settings.EMBEDDING_MODEL_SIZE)

    vdb = VectorDBProviderFactory(config=settings).create(provider=settings.VECTOR_DB_BACKEND)
    vdb.connect()
    bm25 = BM25ProviderFactory(config=settings).create(provider=settings.BM25_BACKEND)

    reranker = None
    if getattr(settings, "RERANKER_ENABLED", False):
        from stores.reranker.RerankerProviderFactory import RerankerProviderFactory
        reranker = RerankerProviderFactory(config=settings).create(provider=settings.RERANKER_BACKEND)
        log.info(f"Reranker: {settings.RERANKER_BACKEND}")

    repo = JsonChunkRepository(storage_path="chunk_staging_buffer.json")
    cache = ContextualDescriptionCache(storage_path="contextual_cache.json")
    return NLPController(
        vectordb_client=vdb, generation_client=gen, embedding_client=emb,
        chunk_repository=repo, reranker_client=reranker, bm25_client=bm25,
        contextual_cache=cache,
    ), vdb


async def main(only_dataset=None, only_config=None, per_level=False, collection=None, top_k=5):
    settings = get_settings()
    oc_key = getattr(settings, "OPENAI_COMPAT_API_KEY", None)
    if not (oc_key or settings.GEMINI_API_KEY or settings.GROQ_API_KEY):
        raise SystemExit("No LLM key set. For Cerebras: set GENERATION_BACKEND=OPENAI_COMPAT "
                         "and OPENAI_COMPAT_API_KEY in .env.")
    judge_kind = "OpenAI-compat (Cerebras)" if oc_key else ("Gemini" if settings.GEMINI_API_KEY else "Groq")
    log.info(f"RAGAS judge: {judge_kind}")

    controller, vdb = build_controller(settings)
    results = load_results()

    for ds_name, base_coll, ctx_coll in DATASETS:
        if only_dataset and ds_name != only_dataset:
            continue
        cases = get_test_cases(dataset=ds_name)
        if per_level:
            # Keep the first question of each difficulty level (1..7) -> a
            # balanced subset that still spans every level but cuts the call
            # count ~2x for the free-tier RPM budget.
            seen, subset = set(), []
            for c in cases:
                lv = c.get("level")
                if lv not in seen:
                    seen.add(lv); subset.append(c)
            cases = subset
            log.info(f"per-level subset: {len(cases)} cases (levels {sorted(seen)})")
        log.info(f"\n{'#'*64}\nDATASET {ds_name}: {len(cases)} cases\n{'#'*64}")
        for cfg_name, fl, coll_kind in LADDER:
            if only_config and cfg_name != only_config:
                continue
            # When a corpus is overridden (e.g. the mixed corpus), retrieve
            # against it and key results by it so they don't clash with the
            # per-doc small-corpus results already saved.
            eff_base = collection or base_coll
            eff_ctx = (collection + "_ctx") if collection else ctx_coll
            tag = f"@{eff_base}" if collection else ""
            key = f"{ds_name}{tag}::{cfg_name}"
            if key in results and results[key].get("scores", {}).get("overall", 0) > 0:
                log.info(f"SKIP {key} (already done)")
                continue
            project_id = eff_ctx if coll_kind == "ctx" else eff_base
            # Skip a contextual-retrieval config if its collection wasn't built
            # (e.g. mixed corpus ingested without --with-ctx) — avoids burning
            # calls on an empty collection.
            if coll_kind == "ctx" and not os.path.exists(
                    os.path.join("bm25_db", f"{project_id}.pkl")):
                log.warning(f"SKIP {key}: contextual collection '{project_id}' not built "
                            f"(re-run ingest with --with-ctx to include it).")
                continue

            log.info(f"\n{'='*60}\nRUN {key}  collection={project_id}  flags={fl}\n{'='*60}")
            t0 = time.time()
            test_cases, test_details = _run_batch(
                controller=controller, project_id=project_id, cases=cases,
                enable_multi_query=fl["mq"], enable_hybrid=fl["hy"],
                enable_reranker=fl["rr"], enable_compression=fl["cp"],
                enable_hyde=fl["hd"], limit=top_k,
            )
            batch_ms = round((time.time() - t0) * 1000)

            evaluator = RAGASEvaluator(
                groq_api_key=settings.GROQ_API_KEY,
                gemini_api_key=settings.GEMINI_API_KEY,
                openai_compat_api_key=getattr(settings, "OPENAI_COMPAT_API_KEY", None),
                openai_compat_base_url=getattr(settings, "OPENAI_COMPAT_BASE_URL", None),
                openai_compat_model=getattr(settings, "OPENAI_COMPAT_MODEL", None),
                timeout=3600,  # 1 hour: reranker/compression batches need RAGAS budget after slow retrieval
            )
            scores = await evaluator.evaluate(test_cases)
            log.info(f"SCORES {key} -> {scores}")

            # Per-question audit trail: metric scores + the actual retrieved
            # contexts + answer + ground truth + query variants so every
            # judgment and RAG-Fusion expansion is inspectable.
            per_q = list(getattr(evaluator, "last_per_question", []) or [])
            for i, tc in enumerate(test_cases):
                rec = per_q[i] if i < len(per_q) else {}
                rec["answer"] = tc.get("answer", "")
                rec["ground_truth"] = tc.get("ground_truth", "")
                rec["contexts"] = tc.get("contexts", [])
                # Store query variants generated by RAG Fusion / HyDE for auditing
                td = test_details[i] if i < len(test_details) else {}
                rec["query_variants"] = td.get("query_variants", [])
                if i >= len(per_q):
                    per_q.append(rec)

            # Log none_counts to surface judge failures clearly
            nc = scores.get("none_counts", {})
            if any(v > 0 for v in nc.values()):
                log.warning(
                    f"RAGAS judge failures for {key}: {nc} out of {len(test_cases)} questions. "
                    f"Faithfulness reported score may be inflated (dropna excludes failures). "
                    f"Re-run with a more reliable judge if these counts are high."
                )

            results[key] = {
                "dataset": ds_name,
                "config": cfg_name,
                "collection": project_id,
                "flags": fl,
                "scores": scores,
                "avg_latency_ms": _avg_latency(test_details),
                "batch_ms": batch_ms,
                "num_cases": len(test_cases),
                "per_question": per_q,
                "test_details": test_details,
            }
            save_results(results)

            # Separate, human-readable dump of exactly what was retrieved for
            # each question under this config (text + score + which document),
            # so the retrieval behaviour can be inspected directly.
            try:
                chunks_path = "retrieved_chunks.json"
                dump = {}
                if os.path.exists(chunks_path):
                    dump = json.load(open(chunks_path))
                dump[key] = []
                for i, tc in enumerate(test_cases):
                    td = test_details[i] if i < len(test_details) else {}
                    ctxs = tc.get("contexts", [])
                    metas = td.get("context_meta", []) or []
                    cscores = td.get("context_scores", []) or []
                    dump[key].append({
                        "question": tc.get("question", ""),
                        "answer": tc.get("answer", ""),
                        "num_chunks": len(ctxs),
                        "chunks": [
                            {
                                "rank": j + 1,
                                "score": (round(cscores[j], 4) if j < len(cscores)
                                          and isinstance(cscores[j], (int, float)) else None),
                                "doc": (metas[j].get("doc_label") or metas[j].get("source")
                                        if j < len(metas) else None),
                                "page": (metas[j].get("page") if j < len(metas) else None),
                                "text": (c[:400] + "…") if len(c) > 400 else c,
                            }
                            for j, c in enumerate(ctxs)
                        ],
                    })
                with open(chunks_path, "w") as f:
                    json.dump(dump, f, indent=2)
            except Exception as e:
                log.warning(f"Could not write retrieved_chunks.json: {e}")

            if "error" in scores:
                log.warning(f"RAGAS reported error on {key}: {scores.get('error')}. "
                            "If this is a quota/429 error, swap in a fresh key and re-run "
                            "(completed configs are skipped).")

    # ── Summary table ────────────────────────────────────────────────────
    log.info("\n\n" + "=" * 78)
    log.info("ABLATION COMPLETE")
    log.info("=" * 78)
    # EvalSR = Evaluation Success Rate (scored cells / total). Read it ALONGSIDE
    # the metric scores: a config is only fairly comparable to another at the
    # same EvalSR. A high score at low EvalSR means few questions were actually
    # judged, so the average is over a small, biased subset.
    hdr = (f"{'dataset/config':<32} {'Faith':>6} {'Relev':>6} {'Prec':>6} "
           f"{'Recall':>6} {'Overall':>7} {'EvalSR':>7}")
    log.info(hdr)
    for key, r in results.items():
        s = r["scores"]
        log.info(f"{key:<32} {s.get('Faithfulness',0):>6.3f} {s.get('AnswerRelevancy',0):>6.3f} "
                 f"{s.get('ContextPrecision',0):>6.3f} {s.get('ContextRecall',0):>6.3f} "
                 f"{s.get('overall',0):>7.3f} {s.get('eval_success_rate',0):>7.3f}")
    vdb.disconnect()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="RAG ablation runner (RAGAS-scored)")
    ap.add_argument("--dataset", choices=["networks", "os_threads"], default=None,
                    help="run only this dataset (default: both)")
    ap.add_argument("--config", default=None,
                    help="run only this config row, e.g. baseline / +hyde / +rag_fusion / "
                         "+hybrid / +reranker / +compression / +contextual")
    ap.add_argument("--per-level", action="store_true",
                    help="evaluate only 1 question per difficulty level (7 cases) "
                         "to fit the free-tier RPM budget")
    ap.add_argument("--collection", default=None,
                    help="override the collection to retrieve against (e.g. rag_mixed "
                         "for the large mixed-corpus run). Results are keyed by it.")
    ap.add_argument("--top-k", type=int, default=5,
                    help="number of chunks retrieved per query (default 5). Use 3 on the "
                         "mixed corpus to make ranking errors costly and expose the layers.")
    a = ap.parse_args()
    asyncio.run(main(only_dataset=a.dataset, only_config=a.config,
                     per_level=a.per_level, collection=a.collection, top_k=a.top_k))
