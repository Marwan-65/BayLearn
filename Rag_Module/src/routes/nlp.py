"""
NLP router
==========

Endpoint definitions for the RAG module. All handler logic lives in
routes/_nlp_handlers.py to keep this file focused on URL patterns and
HTTP response shaping.

Endpoints:
  POST /index/push/{project_id}        - build embeddings + BM25 index
  POST /index/search/{project_id}      - raw dense search (debugging)
  GET  /index/info/{project_id}        - collection stats
  POST /ask/{project_id}               - intent-first RAG
  POST /evaluate/{project_id}          - RAGAS on a batch (single config)
  POST /evaluate/ablation/{project_id} - ablation study across configs

The old /ask/compare and /evaluate/compare endpoints have been
replaced by /evaluate/ablation, which accepts an arbitrary list of
technique-flag combinations so the thesis can measure the contribution
of EVERY layer (multi_query, hybrid, reranker, compression) rather
than just compression on/off.
"""

import asyncio
import datetime
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.limiter import limiter
from evaluation.ragas_evaluator import RAGASEvaluator
from models import Response_Signal
from routes.schemes.nlp import pushRequest, searchRequest
from routes._nlp_handlers import (
    _build_controller,
    _handle_equation_from_context,
    _handle_rag_only,
    _run_batch,
    _avg_latency,
)

logger = logging.getLogger("uvicorn.error")

nlp_router = APIRouter(prefix="/api/v1/nlp")

# ── Async job registry ────────────────────────────────────────────────────────
# Evaluation (single + ablation) runs as a background asyncio task so the HTTP
# request returns immediately with a job_id instead of timing out after minutes.
_eval_jobs: Dict[str, Dict[str, Any]] = {}


async def _run_eval_job(job_id: str, coro):
    """Wrap an evaluation coroutine and store the result in _eval_jobs."""
    try:
        result = await coro
        _eval_jobs[job_id].update({"status": "done", "result": result,
                                   "completed_at": datetime.datetime.now().isoformat()})
    except Exception as exc:
        logger.error(f"Eval job {job_id} failed: {exc}")
        _eval_jobs[job_id].update({"status": "error", "error": str(exc),
                                   "completed_at": datetime.datetime.now().isoformat()})


# =====================================================================
# Indexing / search / info
# =====================================================================

@nlp_router.post("/index/push/{project_id}")
async def index_project(
    project_id: str,
    request: Request,
    push_request: pushRequest,
):
    controller = _build_controller(request)
    project = await controller.validate_project(project_id)
    if not project:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"signal": Response_Signal.PROJECT_NOT_FOUND_ERROR.value},
        )

    inserted = await controller.index_project(
        project_id=project_id,
        do_reset=push_request.do_reset,
    )
    if inserted == 0:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"signal": Response_Signal.INSERT_INTO_VECTORDB_ERROR.value},
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "signal": Response_Signal.INSERT_INTO_VECTORDB_SUCCESS.value,
            "inserted_items_count": inserted,
        },
    )


@nlp_router.post("/index/search/{project_id}")
async def search(
    project_id: str,
    request: Request,
    search_request: searchRequest,
):
    controller = _build_controller(request)
    project = await controller.validate_project(project_id)
    if not project:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"signal": Response_Signal.PROJECT_NOT_FOUND_ERROR.value},
        )

    top_results = controller.search(
        project_id=project_id,
        query=search_request.text,
        limit=search_request.limit,
    )
    if not top_results:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "signal": Response_Signal.SEARCH_VECTORDB_COLLECTION_Failure.value,
                "top_results": [],
            },
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "signal": Response_Signal.SEARCH_VECTORDB_COLLECTION_SUCCESS.value,
            "top_results": top_results,
        },
    )


@nlp_router.get("/index/info/{project_id}")
async def get_nlp_index_info(project_id: str, request: Request):
    controller = _build_controller(request)
    project = await controller.validate_project(project_id)
    if not project:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"signal": Response_Signal.PROJECT_NOT_FOUND_ERROR.value},
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "signal": Response_Signal.GET_VECTORDB_COLLECTION_INFO_SUCCESS.value,
            "collection_info": controller.get_vector_db_collection_info(
                project_id=project_id
            ),
        },
    )


# =====================================================================
# /ask — main RAG endpoint (intent-first routing)
# =====================================================================

@nlp_router.post("/ask/{project_id}")
@limiter.limit("20/minute")
async def ask_question(
    project_id: str,
    request: Request,
    search_request: searchRequest,
):
    endpoint_t0 = time.time()
    controller = _build_controller(request)

    project = await controller.validate_project(project_id)
    if not project:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"signal": Response_Signal.PROJECT_NOT_FOUND_ERROR.value},
        )

    question = search_request.text
    limit = search_request.limit
    # Convert pydantic ChatMessage objects to plain dicts for the controller.
    raw_history = [
        {"role": m.role, "content": m.content}
        for m in (search_request.chat_history or [])
    ]

    # ── Classify intent FIRST ──
    intent_router = getattr(request.app, "intent_router", None)
    intent = "rag_only"
    confidence = 0.0
    extracted_params = {}
    intent_ms = 0

    if intent_router:
        t_intent = time.time()
        classification = intent_router.classify(question)
        intent_ms = round((time.time() - t_intent) * 1000)
        intent = classification["intent"]
        confidence = classification["confidence"]
        extracted_params = classification.get("extracted_params", {})
        logger.info(
            f"Intent: {intent} (confidence: {confidence:.2f}) "
            f"for question: {question[:80]}..."
        )

    # ── Route based on intent ──
    if intent == "equation_from_context":
        response = await _handle_equation_from_context(
            controller, project_id, question, limit, extracted_params, confidence
        )
    else:
        response = await _handle_rag_only(
            controller, project_id, question, limit, chat_history=raw_history
        )
        response["intent"] = "rag_only"

    if not response:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"signal": Response_Signal.AUGMENTED_ANSWER_FAILURE.value},
        )
    if "error" in response and response["error"] != "no_relevant_sources":
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"signal": response["error"]},
        )

    response.setdefault("timings", {})
    response["timings"]["intent_classification_ms"] = intent_ms
    response["timings"]["endpoint_total_ms"] = round(
        (time.time() - endpoint_t0) * 1000
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "signal": Response_Signal.AUGMENTED_ANSWER_SUCCESS.value,
            "data": response,
        },
    )


# =====================================================================
# /evaluate — single-config RAGAS run (non-blocking — returns job_id immediately)
# =====================================================================

async def _do_single_eval(
    controller, project_id, cases_to_evaluate, groq_api_key,
    enable_multi_query, enable_hybrid, enable_reranker, enable_compression,
    dataset, label,
):
    test_cases, test_details = _run_batch(
        controller=controller,
        project_id=project_id,
        cases=cases_to_evaluate,
        enable_multi_query=enable_multi_query,
        enable_hybrid=enable_hybrid,
        enable_reranker=enable_reranker,
        enable_compression=enable_compression,
    )
    evaluator = RAGASEvaluator(groq_api_key=groq_api_key)
    scores = await evaluator.evaluate(test_cases)
    avg_latency = _avg_latency(test_details)
    evaluator.save_results(scores, test_details=test_details, label=label)
    return {
        "signal": "Evaluation completed successfully",
        "scores": scores,
        "avg_latency_ms": avg_latency,
        "num_test_cases": len(test_cases),
        "flags": {
            "multi_query": enable_multi_query,
            "hybrid": enable_hybrid,
            "reranker": enable_reranker,
            "compression": enable_compression,
        },
        "dataset": dataset,
        "test_details": test_details,
    }


@nlp_router.post("/evaluate/{project_id}")
async def evaluate_rag(
    project_id: str,
    request: Request,
    batch_start: int = 0,
    batch_size: int = 5,
    enable_multi_query: Optional[bool] = None,
    enable_hybrid: Optional[bool] = None,
    enable_reranker: Optional[bool] = None,
    enable_compression: Optional[bool] = None,
    dataset: str = "scientific",
    levels: Optional[str] = None,
):
    """
    Start a RAGAS evaluation job (returns immediately).
    Poll GET /evaluate/results/{job_id} for the result.
    Valid datasets: scientific, backend, multimodal.
    """
    controller = _build_controller(request)
    groq_api_key = getattr(request.app.generation_client, "api_key", None)
    from evaluation.test_set import get_test_cases

    try:
        level_filter = [int(x.strip()) for x in levels.split(",")] if levels else None
    except ValueError:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"signal": "Invalid levels parameter: must be comma-separated integers (e.g. '1,2,3')"},
        )
    all_cases = get_test_cases(dataset=dataset, levels=level_filter)
    cases_to_evaluate = all_cases[batch_start: batch_start + batch_size] if batch_size > 0 else all_cases

    label = (
        f"eval_{dataset}"
        f"_mq={enable_multi_query}_hy={enable_hybrid}"
        f"_rr={enable_reranker}_cp={enable_compression}"
    )
    job_id = str(uuid.uuid4())[:8]
    _eval_jobs[job_id] = {"status": "running", "label": label,
                          "started_at": datetime.datetime.now().isoformat()}

    asyncio.create_task(_run_eval_job(job_id, _do_single_eval(
        controller, project_id, cases_to_evaluate, groq_api_key,
        enable_multi_query, enable_hybrid, enable_reranker, enable_compression,
        dataset, label,
    )))

    return JSONResponse(status_code=202, content={
        "signal": "Evaluation started",
        "job_id": job_id,
        "label": label,
        "num_test_cases": len(cases_to_evaluate),
        "poll": f"/api/v1/nlp/evaluate/results/{job_id}",
    })


# =====================================================================
# /evaluate/ablation — multi-run ablation study (thesis-grade)
# =====================================================================

class AblationRun(BaseModel):
    """One row in the ablation study."""
    name: str = Field(..., description="Human-readable label for this run")
    enable_multi_query: Optional[bool] = None
    enable_hybrid: Optional[bool] = None
    enable_reranker: Optional[bool] = None
    enable_compression: Optional[bool] = None


class AblationRequest(BaseModel):
    runs: List[AblationRun] = Field(
        ...,
        description=(
            "List of technique combinations to evaluate. Each run is "
            "executed on the same batch of test cases and compared."
        ),
    )
    batch_start: int = 0
    batch_size: int = 5
    dataset: str = "scientific"
    levels: Optional[str] = None


async def _do_ablation(controller, project_id, cases_to_evaluate, groq_api_key, body):
    from evaluation.test_set import get_test_cases  # already resolved by caller
    results = {}
    for i, run in enumerate(body.runs):
        # ── inter-config cool-down (skip before first run) ──────────────────
        # Groq free tier tokens-per-minute resets every 60s.  Waiting between
        # configs prevents the generation quota from being exhausted and avoids
        # empty-answer rate-limit responses on subsequent runs.
        if i > 0:
            logger.info(
                f"[ablation] Waiting 90s before '{run.name}' to let Groq quota recover …"
            )
            await asyncio.sleep(90)

        test_cases, test_details = _run_batch(
            controller=controller,
            project_id=project_id,
            cases=cases_to_evaluate,
            enable_multi_query=run.enable_multi_query,
            enable_hybrid=run.enable_hybrid,
            enable_reranker=run.enable_reranker,
            enable_compression=run.enable_compression,
        )

        # Timeout = 300s per test-case × n_cases (generous floor: 900s min).
        # This covers max_workers=1 sequential RAGAS calls without a hard cap.
        ragas_timeout = max(900, 300 * len(test_cases))
        evaluator = RAGASEvaluator(groq_api_key=groq_api_key, timeout=ragas_timeout)
        scores = await evaluator.evaluate(test_cases)
        avg_latency = _avg_latency(test_details)
        label = f"ablation_{body.dataset}_{run.name.replace(' ', '_')}"
        evaluator.save_results(scores, test_details=test_details, label=label)
        results[run.name] = {
            "flags": {
                "multi_query": run.enable_multi_query,
                "hybrid": run.enable_hybrid,
                "reranker": run.enable_reranker,
                "compression": run.enable_compression,
            },
            "scores": scores,
            "avg_latency_ms": avg_latency,
            "test_details": test_details,
        }
    return {
        "signal": "Ablation study completed",
        "dataset": body.dataset,
        "num_test_cases": len(cases_to_evaluate),
        "num_runs": len(body.runs),
        "results": results,
    }


@nlp_router.post("/evaluate/ablation/{project_id}")
async def evaluate_ablation(
    project_id: str,
    request: Request,
    body: AblationRequest,
):
    """
    Start an ablation study (returns job_id immediately — non-blocking).
    Poll GET /evaluate/results/{job_id} for the result.

    Example body:
        {
          "runs": [
            {"name": "baseline",     "enable_multi_query": false, "enable_hybrid": false, "enable_reranker": false, "enable_compression": false},
            {"name": "+hybrid",      "enable_multi_query": true,  "enable_hybrid": true,  "enable_reranker": false, "enable_compression": false},
            {"name": "+reranker",    "enable_multi_query": true,  "enable_hybrid": true,  "enable_reranker": true,  "enable_compression": false},
            {"name": "+compression", "enable_multi_query": true,  "enable_hybrid": true,  "enable_reranker": true,  "enable_compression": true}
          ],
          "batch_size": 5,
          "dataset": "scientific"
        }
    Valid datasets: scientific, backend, multimodal.
    """
    controller = _build_controller(request)
    groq_api_key = getattr(request.app.generation_client, "api_key", None)
    from evaluation.test_set import get_test_cases

    try:
        level_filter = [int(x.strip()) for x in body.levels.split(",")] if body.levels else None
    except ValueError:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"signal": "Invalid levels parameter: must be comma-separated integers (e.g. '1,2,3')"},
        )
    all_cases = get_test_cases(dataset=body.dataset, levels=level_filter)
    cases_to_evaluate = (
        all_cases[body.batch_start: body.batch_start + body.batch_size]
        if body.batch_size > 0 else all_cases
    )

    job_id = str(uuid.uuid4())[:8]
    _eval_jobs[job_id] = {
        "status": "running",
        "label": f"ablation_{body.dataset}",
        "num_runs": len(body.runs),
        "num_test_cases": len(cases_to_evaluate),
        "started_at": datetime.datetime.now().isoformat(),
    }

    asyncio.create_task(_run_eval_job(job_id, _do_ablation(
        controller, project_id, cases_to_evaluate, groq_api_key, body,
    )))

    return JSONResponse(status_code=202, content={
        "signal": "Ablation study started",
        "job_id": job_id,
        "num_runs": len(body.runs),
        "num_test_cases": len(cases_to_evaluate),
        "poll": f"/api/v1/nlp/evaluate/results/{job_id}",
    })


# =====================================================================
# /evaluate/results — poll job status / list all saved results
# =====================================================================

@nlp_router.get("/evaluate/results/{job_id}")
async def get_eval_result(job_id: str):
    """Poll a running or completed evaluation job by job_id."""
    job = _eval_jobs.get(job_id)
    if not job:
        return JSONResponse(status_code=404, content={"signal": "Job not found", "job_id": job_id})
    return JSONResponse(status_code=200, content={"job_id": job_id, **job})


@nlp_router.get("/evaluate/results")
async def list_eval_results():
    """Return all saved evaluation results from evaluation_results.json."""
    import os, json as _json
    path = "evaluation_results.json"
    if not os.path.exists(path):
        return JSONResponse(status_code=200, content={"signal": "No results saved yet", "results": []})
    try:
        with open(path) as f:
            history = _json.load(f)
        return JSONResponse(status_code=200, content={"signal": "ok", "count": len(history), "results": history})
    except Exception as e:
        return JSONResponse(status_code=500, content={"signal": f"Failed to read results: {e}"})
