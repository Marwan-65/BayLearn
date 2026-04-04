from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from routes.schemes.nlp import pushRequest, searchRequest
from models import Response_Signal
from controllers import NLPController
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
# WHY: Every route needs the same controller setup.
# Centralizing it here means one place to update when
# new clients (e.g. BM25, RAG-Fusion) are added.
# ---------------------------------------------------------
def _build_controller(request: Request) -> NLPController:
    return NLPController(
        vectordb_client=request.app.vectordb_client,
        generation_client=request.app.generation_client,
        embedding_client=request.app.embedding_client,
        chunk_repository=request.app.chunk_repository,
        reranker_client=getattr(request.app, "reranker_client", None),
    )
 
 
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
# ASK — main RAG endpoint
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
 
    response = controller.generate_augmented_answer(
        project_id=project_id,
        question=search_request.text,
        limit=search_request.limit,
    )
 
    if not response:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"signal": Response_Signal.AUGMENTED_ANSWER_FAILURE.value},
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
# Runs the same question twice and returns both side by side.
# Useful for thesis documentation and manual inspection.
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
 
    # Parse levels filter — e.g. "1,2" → [1, 2]
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
 
    # Average latency across all test cases
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
# Runs full evaluation twice, returns side-by-side scores.
# Perfect for thesis results tables.
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
 