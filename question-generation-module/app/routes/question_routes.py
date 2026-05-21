import logging
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.models.schemas import GenerateQuestionsRequest, GenerateQuestionsResponse

logger = logging.getLogger(__name__)

question_router = APIRouter(prefix="/api/v1/questions", tags=["Question Generation"])


@question_router.post("/generate")
async def generate_questions(
    body: GenerateQuestionsRequest,
    request: Request,
):
    """
    Generate quiz questions from an indexed project's study material.
    
    Requires the RAG module to be running and the project to be indexed first.
    """
    service = request.app.question_service  # set in startup (see main.py)

    try:
        questions, chunks_used = await service.generate(
            project_id=body.project_id,
            num_questions=body.num_questions,
            difficulty=body.difficulty,
            question_type=body.question_type,
            topic=body.topic,
        )
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"signal": str(e)},
        )
    except ConnectionError as e:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"signal": str(e)},
        )
    except Exception as e:
        logger.error(f"Question generation failed: {e}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"signal": "Internal error during question generation."},
        )

    response = GenerateQuestionsResponse(
        project_id=body.project_id,
        topic=body.topic,
        questions=questions,
        total_generated=len(questions),
        chunks_used=chunks_used,
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response.model_dump(),
    )


@question_router.get("/health")
async def health_check():
    """Health check endpoint — the orchestrator in src/ will call this."""
    return JSONResponse(status_code=200, content={"status": "ok"})