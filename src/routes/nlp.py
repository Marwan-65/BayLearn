import asyncio
from fastapi import APIRouter, Request, status, HTTPException
from fastapi.responses import JSONResponse
from routes.schemes.nlp import pushRequest, searchRequest
from models import Response_Signal
from controllers import NLPController
import logging
from evaluation.ragas_evaluator import RAGASEvaluator
from evaluation.test_set import TEST_CASES
from core.limiter import limiter 
logger = logging.getLogger("uvicorn.error")

nlp_router = APIRouter(
    prefix="/api/v1/nlp",
)


# ---------------------------------------------------------
# INDEX PROJECT
# ---------------------------------------------------------
@nlp_router.post("/index/push/{project_id}")
async def index_project(
    project_id: str,
    request: Request,
    push_request: pushRequest
):

    controller = NLPController(
        vectordb_client=request.app.vectordb_client,
        generation_client=request.app.generation_client,
        embedding_client=request.app.embedding_client,
        chunk_repository=request.app.chunk_repository    )

    # Validate project existence
    project = await controller.validate_project(project_id)

    if not project:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "signal": Response_Signal.PROJECT_NOT_FOUND_ERROR.value
            }
        )

    # Index with pagination handled inside controller
    inserted_items_count = await controller.index_project(
        project_id=project_id,
        do_reset=push_request.do_reset
    )

    if inserted_items_count == 0:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "signal": Response_Signal.INSERT_INTO_VECTORDB_ERROR.value
            }
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "signal": Response_Signal.INSERT_INTO_VECTORDB_SUCCESS.value,
            "inserted_items_count": inserted_items_count
        }
    )


# ---------------------------------------------------------
# SEARCH PROJECT
# ---------------------------------------------------------
@nlp_router.post("/index/search/{project_id}")
async def search(
    project_id: str,
    request: Request,
    search_request: searchRequest
):

    controller = NLPController(
        vectordb_client=request.app.vectordb_client,
        generation_client=request.app.generation_client,
        embedding_client=request.app.embedding_client,
        chunk_repository=request.app.chunk_repository,
    )

    # Validate project existence
    project = await controller.validate_project(project_id)

    if not project:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "signal": Response_Signal.PROJECT_NOT_FOUND_ERROR.value
            }
        )

    top_results = controller.search(
        project_id=project_id,
        query=search_request.text,
        limit=search_request.limit
    )

    if not top_results:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "signal": Response_Signal.SEARCH_VECTORDB_COLLECTION_Failure.value,
                "top_results": []
            }
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "signal": Response_Signal.SEARCH_VECTORDB_COLLECTION_SUCCESS.value,
            "top_results": top_results
        }
    )


# ---------------------------------------------------------
# COLLECTION INFO
# ---------------------------------------------------------
@nlp_router.get("/index/info/{project_id}")
async def get_nlp_index_info(
    project_id: str,
    request: Request
):

    controller = NLPController(
        vectordb_client=request.app.vectordb_client,
        generation_client=request.app.generation_client,
        embedding_client=request.app.embedding_client,
        chunk_repository=request.app.chunk_repository,
    )

    # Validate project existence
    project = await controller.validate_project(project_id)

    if not project:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "signal": Response_Signal.PROJECT_NOT_FOUND_ERROR.value
            }
        )

    collection_info = controller.get_vector_db_collection_info(
        project_id=project_id
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "signal": Response_Signal.GET_VECTORDB_COLLECTION_INFO_SUCCESS.value,
            "collection_info": collection_info
        }
    )
@nlp_router.post("/ask/{project_id}")
@limiter.limit("20/minute")
async def ask_question(
        project_id: str,
        request: Request,
        search_request: searchRequest
    ):

        controller = NLPController(
            vectordb_client=request.app.vectordb_client,
            generation_client=request.app.generation_client,
            embedding_client=request.app.embedding_client,
            chunk_repository=request.app.chunk_repository
        )

        project = await controller.validate_project(project_id)
        print("Project validation result:", project)  # Debug log

        if not project:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "signal": Response_Signal.PROJECT_NOT_FOUND_ERROR.value
                }
            )

        response =  controller.generate_augmented_answer(
            project_id=project_id,
            question=search_request.text,
            limit=search_request.limit
        )

        if not response:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "signal": Response_Signal.AUGMENTED_ANSWER_FAILURE.value
                }
            )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "signal": Response_Signal.AUGMENTED_ANSWER_SUCCESS.value,
                "data": response
            }
        )


@nlp_router.post("/evaluate/{project_id}")
async def evaluate_rag(project_id: str, request: Request):

    controller = NLPController(
        vectordb_client=request.app.vectordb_client,
        generation_client=request.app.generation_client,
        embedding_client=request.app.embedding_client,
        chunk_repository=request.app.chunk_repository
    )

    from evaluation.test_set import TEST_CASES
    from evaluation.ragas_evaluator import RAGASEvaluator

    test_cases = []
    #cases_to_evaluate = TEST_CASES[batch_start:batch_start+batch_size] if batch_size > 0 else TEST_CASES
    for case in TEST_CASES:
        rag_response = controller.generate_augmented_answer(
            project_id=project_id,
            question=case["question"],
            limit=5
        )
        logger.info(f"Question: {case['question']}")
        logger.info(f"Full RAG response: {rag_response}")
    
        # IMPORTANT: contexts must be a list of strings
        #sources = rag_response.get("sources", [])
        context_before = rag_response.get("context_before_compression", "")
        context_after = rag_response.get("context_after_compression", "")
        # if isinstance(sources, str):
        #     sources = [sources]
        # elif not isinstance(sources, list):
        #     sources = []
        stats = RAGASEvaluator.compute_token_stats(context_before,context_after)
        before_tokens = stats["before_tokens"]
        after_tokens = stats["after_tokens"]
        reduction = stats["reduction_ratio"]
        test_cases.append({
            "question": case["question"],
            "answer": rag_response.get("answer", ""),
            "contexts": [context_after], # list of strings
            "ground_truth": case["ground_truth"],
            "before_tokens": before_tokens,
            "after_tokens": after_tokens,
            "reduction_ratio" : reduction,
        })

    evaluator = RAGASEvaluator(
        groq_api_key=request.app.generation_client.api_key
    )
    scores = await evaluator.evaluate(test_cases)
    # Compute average token stats
    avg_before = sum(tc["before_tokens"] for tc in test_cases) / len(test_cases)
    avg_after = sum(tc["after_tokens"] for tc in test_cases) / len(test_cases)
    avg_reduction = sum(tc["reduction_ratio"] for tc in test_cases) / len(test_cases)

    scores["avg_before_tokens"] = round(avg_before, 1)
    scores["avg_after_tokens"] = round(avg_after, 1)
    scores["avg_reduction_ratio"] = round(avg_reduction, 3)
    
    evaluator.save_results(scores, output_path="with_compression.json")
    evaluator.save_results(scores, output_path="without_compression.json")
    logger.info(
        f"[{case['question']}] → before: {before_tokens}, after: {after_tokens}, reduction: {reduction}"
    )       
    return JSONResponse(
        status_code=200,
        content={
            "signal": "Evaluation completed successfully",
            "scores": scores,
            "num_test_cases": len(test_cases),
            "test_details": [
                {
                    "question": tc["question"],
                    "answer_preview": tc["answer"][:100] + "...",
                    "num_contexts": len(tc["contexts"]),
                    # compression metrics
                    "before_tokens": tc.get("before_tokens", 0),
                    "after_tokens": tc.get("after_tokens", 0),
                    "reduction_ratio": tc.get("reduction_ratio", 0.0)
                }
                for tc in test_cases
            ]
        }
    )