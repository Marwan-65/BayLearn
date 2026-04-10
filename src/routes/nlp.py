from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from routes.schemes.nlp import pushRequest, searchRequest
from models import Response_Signal
from controllers import NLPController
from controllers.intent_router import IntentRouter
import httpx
import logging
import time

from evaluation.ragas_evaluator import RAGASEvaluator
from evaluation.test_set import TEST_CASES
from core.limiter import limiter

logger = logging.getLogger("uvicorn.error")

nlp_router = APIRouter(
    prefix="/api/v1/nlp",
)


# ---------------------------------------------------------
# Helper: build NLPController with all clients
# ---------------------------------------------------------
def _build_controller(request: Request) -> NLPController:
    return NLPController(
        vectordb_client=request.app.vectordb_client,
        generation_client=request.app.generation_client,
        embedding_client=request.app.embedding_client,
        chunk_repository=request.app.chunk_repository,
        reranker_client=getattr(request.app, "reranker_client", None),
        bm25_client=getattr(request.app, "bm25_client", None),
    )


# ═════════════════════════════════════════════════════════════
# Phase 1: Intent-First Orchestration
# ═════════════════════════════════════════════════════════════
# OLD FLOW:  question -> RAG answer -> classify intent -> maybe call module
# NEW FLOW:  question -> classify intent -> route to correct pipeline
#
# This saves an LLM generation call when user wants equation/animation,
# and ensures module inputs come from REAL retrieved sources (Phase 2).
# ═════════════════════════════════════════════════════════════

async def _handle_rag_only(
    controller: NLPController,
    project_id: str,
    question: str,
    limit: int,
) -> dict:
    """Standard RAG pipeline: retrieve + generate answer."""
    retrieval = controller.retrieve_sources(
        project_id=project_id,
        question=question,
        limit=limit,
        intent="rag_only",
    )

    if "error" in retrieval:
        if retrieval["error"] == "no_relevant_sources":
            return {
                "intent": "rag_only",
                "query": question,
                "answer": (
                    "I could not find relevant information in the "
                    "uploaded materials to answer this question."
                ),
                "sources": [],
                "scores": [],
                "num_sources": 0,
                **_retrieval_metadata(retrieval),
            }
        return {"intent": "rag_only", **retrieval}

    filtered_results = retrieval["filtered_results"]
    timings = retrieval["timings"]

    answer = controller.generate_answer_from_sources(
        question=question,
        filtered_results=filtered_results,
        timings=timings,
    )

    timings["total_ms"] = sum(timings.values())

    return {
        "intent": "rag_only",
        "query": question,
        "answer": answer,
        **_sources_payload(filtered_results, controller),
        **_retrieval_metadata(retrieval),
    }


async def _handle_equation_from_context(
    controller: NLPController,
    project_id: str,
    question: str,
    limit: int,
    extracted_params: dict,
    confidence: float,
) -> dict:
    """
    Phase 1+2: Retrieve sources with intent-aware compression,
    extract equation from REAL sources, call equation module.
    Also generates a RAG explanation alongside the equation solution.
    """
    from helpers.config import get_settings
    settings = get_settings()

    retrieval = controller.retrieve_sources(
        project_id=project_id,
        question=question,
        limit=limit,
        intent="equation_from_context",
    )

    if "error" in retrieval:
        if retrieval["error"] == "no_relevant_sources":
            return {
                "intent": "equation_from_context",
                "query": question,
                "answer": (
                    "I could not find relevant equations in the "
                    "uploaded materials for this question."
                ),
                "equation_result": None,
                "sources": [],
                "scores": [],
                "num_sources": 0,
                **_retrieval_metadata(retrieval),
            }
        return {"intent": "equation_from_context", **retrieval}

    filtered_results = retrieval["filtered_results"]
    timings = retrieval["timings"]

    # Phase 2: Extract equation from REAL retrieved sources
    t0 = time.time()
    equation_text = controller.extract_equation_from_sources(
        filtered_results=filtered_results,
        question=question,
    )
    timings["equation_extraction_ms"] = round((time.time() - t0) * 1000)

    # Call equation module
    equation_result = None
    base_url = getattr(settings, "EQUATION_MODULE_URL", None)
    if base_url:
        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{base_url.rstrip('/')}/run",
                    json={"query": equation_text},
                )
                if resp.status_code == 200:
                    equation_result = resp.json()
                else:
                    logger.warning(
                        f"Equation module returned {resp.status_code}: "
                        f"{resp.text[:200]}"
                    )
        except httpx.ConnectError:
            logger.warning(f"Equation module not running at {base_url}")
        except Exception as e:
            logger.warning(f"Equation module call failed: {e}")
        timings["equation_module_ms"] = round((time.time() - t0) * 1000)
    else:
        logger.warning("EQUATION_MODULE_URL not configured")

    # Also generate a RAG explanation for context
    answer = controller.generate_answer_from_sources(
        question=question,
        filtered_results=filtered_results,
        timings=timings,
    )

    timings["total_ms"] = sum(timings.values())

    return {
        "intent": "equation_from_context",
        "intent_confidence": confidence,
        "query": question,
        "answer": answer,
        "equation_text_sent": equation_text,
        "equation_result": equation_result,
        **_sources_payload(filtered_results, controller),
        **_retrieval_metadata(retrieval),
    }


async def _handle_animation_from_context(
    controller: NLPController,
    project_id: str,
    question: str,
    limit: int,
    extracted_params: dict,
    confidence: float,
) -> dict:
    """
    Phase 1+2: Retrieve sources, extract animation parameters from
    REAL sources (not just classifier guesses), return animation spec.
    """
    retrieval = controller.retrieve_sources(
        project_id=project_id,
        question=question,
        limit=limit,
        intent="animation_from_context",
    )

    if "error" in retrieval:
        if retrieval["error"] == "no_relevant_sources":
            return {
                "intent": "animation_from_context",
                "query": question,
                "answer": (
                    "I could not find relevant content in the "
                    "uploaded materials to build an animation."
                ),
                "animation_spec": None,
                "sources": [],
                "scores": [],
                "num_sources": 0,
                **_retrieval_metadata(retrieval),
            }
        return {"intent": "animation_from_context", **retrieval}

    filtered_results = retrieval["filtered_results"]
    timings = retrieval["timings"]

    # Phase 2: Extract animation params from REAL sources + classifier hints
    t0 = time.time()
    animation_spec = controller.extract_animation_params_from_sources(
        filtered_results=filtered_results,
        question=question,
        classifier_params=extracted_params,
    )
    timings["animation_extraction_ms"] = round((time.time() - t0) * 1000)

    # Generate a brief RAG explanation alongside the animation
    answer = controller.generate_answer_from_sources(
        question=question,
        filtered_results=filtered_results,
        timings=timings,
    )

    timings["total_ms"] = sum(timings.values())

    return {
        "intent": "animation_from_context",
        "intent_confidence": confidence,
        "query": question,
        "answer": answer,
        "animation_spec": animation_spec,
        **_sources_payload(filtered_results, controller),
        **_retrieval_metadata(retrieval),
    }


def _sources_payload(filtered_results: list, controller: NLPController) -> dict:
    """Build the sources portion of the response."""
    return {
        "sources": [r["payload"].get("text", "") for r in filtered_results],
        "scores": [r["score"] for r in filtered_results],
        "rerank_scores": (
            [r.get("rerank_score") for r in filtered_results]
            if controller.reranker_client is not None else []
        ),
        "num_sources": len(filtered_results),
    }


def _retrieval_metadata(retrieval: dict) -> dict:
    """Extract common retrieval metadata for the response."""
    return {
        "multi_query_used": retrieval.get("multi_query_used", False),
        "query_variants": retrieval.get("query_variants", []),
        "reranker_used": retrieval.get("reranker_used", False),
        "hybrid_used": retrieval.get("hybrid_used", False),
        "bm25_count": retrieval.get("bm25_count", 0),
        "fusion_sources": retrieval.get("fuse_labels", []),
        "compression_used": retrieval.get("compression_used", False),
        "compression_ratios": retrieval.get("compression_ratios", []),
        "timings": retrieval.get("timings", {}),
    }


# ---------------------------------------------------------
# INDEX PROJECT
# ---------------------------------------------------------
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

    inserted_items_count = await controller.index_project(
        project_id=project_id,
        do_reset=push_request.do_reset,
    )

    if inserted_items_count == 0:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"signal": Response_Signal.INSERT_INTO_VECTORDB_ERROR.value},
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "signal": Response_Signal.INSERT_INTO_VECTORDB_SUCCESS.value,
            "inserted_items_count": inserted_items_count,
        },
    )


# ---------------------------------------------------------
# SEARCH PROJECT
# ---------------------------------------------------------
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


# ---------------------------------------------------------
# COLLECTION INFO
# ---------------------------------------------------------
@nlp_router.get("/index/info/{project_id}")
async def get_nlp_index_info(project_id: str, request: Request):
    controller = _build_controller(request)

    project = await controller.validate_project(project_id)
    if not project:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"signal": Response_Signal.PROJECT_NOT_FOUND_ERROR.value},
        )

    collection_info = controller.get_vector_db_collection_info(project_id=project_id)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "signal": Response_Signal.GET_VECTORDB_COLLECTION_INFO_SUCCESS.value,
            "collection_info": collection_info,
        },
    )


# ---------------------------------------------------------
# ASK — main RAG endpoint (Phase 1: Intent-First Routing)
# ---------------------------------------------------------
@nlp_router.post("/ask/{project_id}")
@limiter.limit("20/minute")
async def ask_question(
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

    question = search_request.text
    limit = search_request.limit

    # Phase 6: Security — enforce input length limit
    from helpers.config import get_settings
    settings = get_settings()
    max_chars = getattr(settings, "INPUT_DEFAULT_MAX_CHARACTERS", 10000)
    if len(question) > max_chars:
        question = question[:max_chars]

    # ─── Phase 1: Classify intent FIRST ───────────────────────
    intent_router = getattr(request.app, "intent_router", None)
    intent = "rag_only"
    confidence = 0.0
    extracted_params = {}

    if intent_router:
        t0 = time.time()
        classification = intent_router.classify(question)
        intent = classification["intent"]
        confidence = classification["confidence"]
        extracted_params = classification.get("extracted_params", {})
        logger.info(
            f"Intent: {intent} (confidence: {confidence:.2f}) "
            f"for question: {question[:80]}..."
        )

    # ─── Route to correct pipeline based on intent ────────────
    if intent == "equation_from_context":
        response = await _handle_equation_from_context(
            controller=controller,
            project_id=project_id,
            question=question,
            limit=limit,
            extracted_params=extracted_params,
            confidence=confidence,
        )
    elif intent == "animation_from_context":
        response = await _handle_animation_from_context(
            controller=controller,
            project_id=project_id,
            question=question,
            limit=limit,
            extracted_params=extracted_params,
            confidence=confidence,
        )
    else:
        response = await _handle_rag_only(
            controller=controller,
            project_id=project_id,
            question=question,
            limit=limit,
        )

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

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "signal": Response_Signal.AUGMENTED_ANSWER_SUCCESS.value,
            "data": response,
        },
    )


# ---------------------------------------------------------
# ASK COMPARE — A/B test compression ON vs OFF
# (Backward-compatible, uses old single-call interface)
# ---------------------------------------------------------
@nlp_router.post("/ask/compare/{project_id}")
@limiter.limit("10/minute")
async def ask_compare(
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

    # Run WITHOUT compression
    t0 = time.time()
    response_without = controller.generate_augmented_answer(
        project_id=project_id,
        question=search_request.text,
        limit=search_request.limit,
        enable_compression=False,
    )
    latency_without = round(time.time() - t0, 3)

    # Run WITH compression
    t0 = time.time()
    response_with = controller.generate_augmented_answer(
        project_id=project_id,
        question=search_request.text,
        limit=search_request.limit,
        enable_compression=True,
    )
    latency_with = round(time.time() - t0, 3)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "signal": "A/B comparison completed",
            "question": search_request.text,
            "without_compression": {
                "answer": response_without.get("answer", ""),
                "sources": response_without.get("sources", []),
                "scores": response_without.get("scores", []),
                "rerank_scores": response_without.get("rerank_scores", []),
                "num_sources": response_without.get("num_sources", 0),
                "timings": response_without.get("timings", {}),
                "latency_seconds": latency_without,
            },
            "with_compression": {
                "answer": response_with.get("answer", ""),
                "sources": response_with.get("sources", []),
                "scores": response_with.get("scores", []),
                "rerank_scores": response_with.get("rerank_scores", []),
                "num_sources": response_with.get("num_sources", 0),
                "compression_ratios": response_with.get("compression_ratios", []),
                "timings": response_with.get("timings", {}),
                "latency_seconds": latency_with,
            },
        },
    )


# ---------------------------------------------------------
# EVALUATE — run RAGAS on a batch of test cases
# ---------------------------------------------------------
@nlp_router.post("/evaluate/{project_id}")
async def evaluate_rag(
    project_id: str,
    request: Request,
    batch_start: int = 0,
    batch_size: int = 5,
    enable_compression: bool = None,
    dataset: str = "cv",
    levels: str = None,
):
    controller = _build_controller(request)

    from evaluation.test_set import get_test_cases

    level_filter = None
    if levels:
        level_filter = [int(l.strip()) for l in levels.split(",")]

    all_cases = get_test_cases(dataset=dataset, levels=level_filter)
    cases_to_evaluate = (
        all_cases[batch_start : batch_start + batch_size]
        if batch_size > 0
        else all_cases
    )

    test_cases = []
    test_details = []

    for case in cases_to_evaluate:
        rag_response = controller.generate_augmented_answer(
            project_id=project_id,
            question=case["question"],
            limit=5,
            enable_compression=enable_compression,
        )
        logger.info(f"Question: {case['question']}")
        logger.info(f"Full RAG response: {rag_response}")

        sources = rag_response.get("sources", [])
        if isinstance(sources, str):
            sources = [sources]
        elif not isinstance(sources, list):
            sources = []

        test_cases.append({
            "question": case["question"],
            "answer": rag_response.get("answer", ""),
            "contexts": sources,
            "ground_truth": case["ground_truth"],
        })

        test_details.append({
            "question": case["question"],
            "level": case.get("level"),
            "answer": rag_response.get("answer", "")[:200],
            "num_contexts": len(sources),
            "timings": rag_response.get("timings", {}),
            "rerank_scores": rag_response.get("rerank_scores", []),
            "compression_ratios": rag_response.get("compression_ratios", []),
        })

    evaluator = RAGASEvaluator(
        groq_api_key=request.app.generation_client.api_key
    )
    scores = await evaluator.evaluate(test_cases)

    all_timings = [d["timings"] for d in test_details if d["timings"]]
    avg_latency = {}
    if all_timings:
        for key in all_timings[0]:
            avg_latency[key] = round(
                sum(t.get(key, 0) for t in all_timings) / len(all_timings)
            )

    label = f"eval_{dataset}_compression={'on' if enable_compression else 'off'}"
    evaluator.save_results(scores, test_details=test_details, label=label)

    return JSONResponse(
        status_code=200,
        content={
            "signal": "Evaluation completed successfully",
            "scores": scores,
            "avg_latency_ms": avg_latency,
            "num_test_cases": len(test_cases),
            "compression_enabled": enable_compression,
            "dataset": dataset,
            "test_details": test_details,
        },
    )


# ---------------------------------------------------------
# EVALUATE COMPARE — A/B RAGAS scores compression ON vs OFF
# ---------------------------------------------------------
@nlp_router.post("/evaluate/compare/{project_id}")
async def evaluate_compare(
    project_id: str,
    request: Request,
    batch_start: int = 0,
    batch_size: int = 5,
    dataset: str = "cv",
    levels: str = None,
):
    controller = _build_controller(request)

    from evaluation.test_set import get_test_cases

    level_filter = None
    if levels:
        level_filter = [int(l.strip()) for l in levels.split(",")]

    all_cases = get_test_cases(dataset=dataset, levels=level_filter)
    cases_to_evaluate = (
        all_cases[batch_start : batch_start + batch_size]
        if batch_size > 0
        else all_cases
    )

    results = {}
    for mode, compression_flag in [
        ("without_compression", False),
        ("with_compression", True),
    ]:
        test_cases = []
        test_details = []

        for case in cases_to_evaluate:
            rag_response = controller.generate_augmented_answer(
                project_id=project_id,
                question=case["question"],
                limit=5,
                enable_compression=compression_flag,
            )

            sources = rag_response.get("sources", [])
            if isinstance(sources, str):
                sources = [sources]
            elif not isinstance(sources, list):
                sources = []

            test_cases.append({
                "question": case["question"],
                "answer": rag_response.get("answer", ""),
                "contexts": sources,
                "ground_truth": case["ground_truth"],
            })
            test_details.append({
                "question": case["question"],
                "level": case.get("level"),
                "answer": rag_response.get("answer", "")[:200],
                "num_contexts": len(sources),
                "timings": rag_response.get("timings", {}),
                "rerank_scores": rag_response.get("rerank_scores", []),
                "compression_ratios": rag_response.get("compression_ratios", []),
            })

        evaluator = RAGASEvaluator(
            groq_api_key=request.app.generation_client.api_key
        )
        scores = await evaluator.evaluate(test_cases)

        all_timings = [d["timings"] for d in test_details if d["timings"]]
        avg_latency = {}
        if all_timings:
            for key in all_timings[0]:
                avg_latency[key] = round(
                    sum(t.get(key, 0) for t in all_timings) / len(all_timings)
                )

        label = f"compare_{dataset}_{mode}"
        evaluator.save_results(scores, test_details=test_details, label=label)

        results[mode] = {
            "scores": scores,
            "avg_latency_ms": avg_latency,
            "test_details": test_details,
        }

    return JSONResponse(
        status_code=200,
        content={
            "signal": "A/B evaluation comparison completed",
            "dataset": dataset,
            "num_test_cases": len(cases_to_evaluate),
            **results,
        },
    )
