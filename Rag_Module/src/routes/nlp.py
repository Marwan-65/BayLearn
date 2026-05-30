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

import logging
import time
from typing import List, Optional

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.limiter import limiter
from evaluation.ragas_evaluator import RAGASEvaluator
from models import Response_Signal
from routes.schemes.nlp import pushRequest, searchRequest
from routes._nlp_handlers import (
    _build_controller,
    _handle_animation_from_context,
    _handle_equation_from_context,
    _handle_rag_only,
    _run_batch,
    _avg_latency,
)

logger = logging.getLogger("uvicorn.error")

nlp_router = APIRouter(prefix="/api/v1/nlp")


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

    # Length enforcement is in pydantic (searchRequest.max_length=5000).
    question = search_request.text
    limit = search_request.limit

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
    elif intent == "animation_from_context":
        response = await _handle_animation_from_context(
            controller, project_id, question, limit, extracted_params, confidence
        )
    else:
        response = await _handle_rag_only(
            controller, project_id, question, limit
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
# /evaluate — single-config RAGAS run
# =====================================================================

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
    dataset: str = "cv",
    levels: Optional[str] = None,
):
    """
    Run RAGAS on a batch of test cases with a single technique config.

    Each enable_* query param accepts true/false/omitted:
      - true  = force the technique on
      - false = force it off
      - omit  = use config default
    """
    controller = _build_controller(request)
    from evaluation.test_set import get_test_cases

    level_filter = None
    if levels:
        level_filter = [int(x.strip()) for x in levels.split(",")]

    all_cases = get_test_cases(dataset=dataset, levels=level_filter)
    cases_to_evaluate = (
        all_cases[batch_start: batch_start + batch_size]
        if batch_size > 0 else all_cases
    )

    test_cases, test_details = _run_batch(
        controller=controller,
        project_id=project_id,
        cases=cases_to_evaluate,
        enable_multi_query=enable_multi_query,
        enable_hybrid=enable_hybrid,
        enable_reranker=enable_reranker,
        enable_compression=enable_compression,
    )

    evaluator = RAGASEvaluator(
        groq_api_key=request.app.generation_client.api_key
    )
    scores = await evaluator.evaluate(test_cases)
    avg_latency = _avg_latency(test_details)

    label = (
        f"eval_{dataset}"
        f"_mq={enable_multi_query}_hy={enable_hybrid}"
        f"_rr={enable_reranker}_cp={enable_compression}"
    )
    evaluator.save_results(scores, test_details=test_details, label=label)

    return JSONResponse(
        status_code=200,
        content={
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
        },
    )


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
    dataset: str = "cv"
    levels: Optional[str] = None


@nlp_router.post("/evaluate/ablation/{project_id}")
async def evaluate_ablation(
    project_id: str,
    request: Request,
    body: AblationRequest,
):
    """
    Run an ablation study: the same batch of test cases is evaluated under
    multiple technique combinations, then RAGAS is computed for each run
    so you can compare them side by side.

    Example body:
        {
          "runs": [
            {"name": "baseline",     "enable_multi_query": false, "enable_hybrid": false, "enable_reranker": false, "enable_compression": false},
            {"name": "+multi_query", "enable_multi_query": true,  "enable_hybrid": false, "enable_reranker": false, "enable_compression": false},
            {"name": "+hybrid",      "enable_multi_query": true,  "enable_hybrid": true,  "enable_reranker": false, "enable_compression": false},
            {"name": "+reranker",    "enable_multi_query": true,  "enable_hybrid": true,  "enable_reranker": true,  "enable_compression": false},
            {"name": "+compression", "enable_multi_query": true,  "enable_hybrid": true,  "enable_reranker": true,  "enable_compression": true}
          ],
          "batch_size": 20,
          "dataset": "cv"
        }

    Replaces the old /ask/compare and /evaluate/compare (compression-only)
    endpoints with a general technique-ablation harness.
    """
    controller = _build_controller(request)
    from evaluation.test_set import get_test_cases

    level_filter = None
    if body.levels:
        level_filter = [int(x.strip()) for x in body.levels.split(",")]

    all_cases = get_test_cases(dataset=body.dataset, levels=level_filter)
    cases_to_evaluate = (
        all_cases[body.batch_start: body.batch_start + body.batch_size]
        if body.batch_size > 0 else all_cases
    )

    results = {}
    for run in body.runs:
        test_cases, test_details = _run_batch(
            controller=controller,
            project_id=project_id,
            cases=cases_to_evaluate,
            enable_multi_query=run.enable_multi_query,
            enable_hybrid=run.enable_hybrid,
            enable_reranker=run.enable_reranker,
            enable_compression=run.enable_compression,
        )
        evaluator = RAGASEvaluator(
            groq_api_key=request.app.generation_client.api_key
        )
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

    return JSONResponse(
        status_code=200,
        content={
            "signal": "Ablation study completed",
            "dataset": body.dataset,
            "num_test_cases": len(cases_to_evaluate),
            "num_runs": len(body.runs),
            "results": results,
        },
    )
