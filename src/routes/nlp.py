from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from routes.schemes.nlp import pushRequest, searchRequest
from models import Response_Signal
from controllers.project import NLPController
import logging

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
        chunk_repository=request.app.chunk_repository,
        project_repository=request.app.project_repository 
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
        project_repository=request.app.project_repository
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
        top_k=search_request.limit
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
        project_repository=request.app.project_repository
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
