import logging
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.models.schemas import GenerateQuestionsRequest, GenerateQuestionsResponse, CheckAnswerRequest, CheckAnswerResponse

logger = logging.getLogger(__name__)

question_router = APIRouter(prefix="/api/v1/questions", tags=["Question Generation"])

@question_router.post("/generate")
async def generate_questions(
    body: GenerateQuestionsRequest,
    request: Request,
):
    """
    generates quiz questions given the concept and difficulty
    Requires the rag module to be running and the file to be indexed first in
    order to reuse the indexing to fetch relevant chunks to the question concept
    """
    service = request.app.question_service  # set in startup (see main.py)

    try:
        questions, chunks_used = await service.generate(
            project_id=body.project_id,
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


@question_router.post("/check")
async def check_answer(body: CheckAnswerRequest, request: Request):
    """
    Grade a student's answer against the expected answer.

    Returns is_correct plus the grading method and (for short answers) the
    similarity/match score. mcq and true and false are exact comparisons; the
    frontend grades those locally for zero latency and only calls this for
    short_answer, where semantic similarity meaningfully improves accuracy.
    """
    grader = getattr(request.app, "answer_grader", None)
    if grader is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"signal": "Answer grader not initialized."},
        )

    try:
        result = grader.grade(
            question_type=body.question_type,
            user_answer=body.user_answer,
            correct_answer=body.correct_answer,
            keywords=body.keywords_to_match,
            options=body.options,
        )
    except Exception as e:
        logger.error(f"Answer grading failed: {e}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"signal": "Internal error during answer grading."},
        )

    # If this answer belongs to an adaptive session, record the result so the
    # rl agent GET answer long-poll can pick it up
    if body.session_id:
        store = getattr(request.app, "adaptive_sessions", None)
        if store is not None:
            store.record_answer(body.session_id, result.is_correct, result.score)

    response = CheckAnswerResponse(
        is_correct=result.is_correct,
        method=result.method,
        score=result.score,
        correct_answer=body.correct_answer,
    )
    return JSONResponse(status_code=status.HTTP_200_OK, content=response.model_dump())


@question_router.get("/health")
async def health_check():
    return JSONResponse(status_code=200, content={"status": "ok"})