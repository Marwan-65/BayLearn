"""
Adaptive agent driven quiz loop routes

The RL agent drives the quiz and the student answers in the frontend
These endpoints coordinate the two via the in memory session store

POST /api/v1/questions/adaptive/{session_id}/config    frontend sets source files
POST /api/v1/questions/adaptive/{session_id}/generate  agent requests a question
GET  /api/v1/questions/adaptive/{session_id}/current   frontend polls for question
GET  /api/v1/questions/adaptive/{session_id}/answer    agent long polls for result

The student answer is recorded by POST /api/v1/questions/check when it carries a session_id
"""

import asyncio
import logging
import time

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.models.schemas import AdaptiveConfigRequest, AdaptiveGenerateRequest

logger = logging.getLogger(__name__)

adaptive_router = APIRouter(prefix="/api/v1/questions/adaptive", tags=["Adaptive Loop"])

@adaptive_router.post("/{session_id}/config")
async def register_session_files(session_id: str, body: AdaptiveConfigRequest, request: Request):
    # Frontend registers which files the agent questions come from so the agent knows the source
    request.app.adaptive_sessions.config(
        session_id, body.file_ids, body.question_type
    )
    return {"signal": "ok", "session_id": session_id, "file_ids": body.file_ids}


@adaptive_router.post("/{session_id}/generate")
async def adaptive_generate_question(session_id: str, body: AdaptiveGenerateRequest, request: Request):
    # Agent asks for a question at a chosen topic and difficulty so the quiz adapts to the student
    store = request.app.adaptive_sessions
    cfg = store.get_config(session_id)
    if not cfg["file_ids"]:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"signal": "Session not configured Frontend must POST config with file_ids first"},
        )

    service = request.app.question_service
    difficulty = (body.difficulty).lower()
    qtype = body.question_type 

    # Multiple candidates are requested because validation may reject low quality questions
    # 
    questions = []
    chunks_used = 0
    last_error = None
    for retry_count in range(3):
        try:
            qs, chunks_used = await service.generate(
                project_id=cfg["file_ids"],
                num_questions=3,
                difficulty=difficulty,
                question_type=qtype,
                topic=body.topic,
            )
        except Exception as e:
            last_error = e
            logger.error(f"Adaptive generate attempt {retry_count + 1} failed: {e}", exc_info=True)
            continue
        if qs:
            questions = qs
            break
        logger.warning(f"Adaptive generate attempt {retry_count + 1}: all candidates rejected by validator retrying")

    if not questions:
        msg = (
            f"Generation failed {last_error}" if last_error
            else "No question passed validation after 3 attempts Try a different topic or difficulty"
        )
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"signal": msg})

    # Card shape matches frontend
    card = {
        "question": questions[0].model_dump(),
        "questionType": qtype,
        "topic": body.topic or "General",
        "difficulty": difficulty,
        "chunksUsed": chunks_used,
    }
    version = store.set_question(session_id, card)
    return {"signal": "ok", "version": version, **card}


@adaptive_router.get("/{session_id}/current")
async def current_question(session_id: str, request: Request):
    # Frontend polls this to know when a new question is available
    return request.app.adaptive_sessions.get_current(session_id)


@adaptive_router.get("/{session_id}/answer")
async def get_answer(session_id: str, request: Request, timeout: float = 55.0):
    # Agent long polls for the student result so it can adapt based on correctness
    store = request.app.adaptive_sessions
    deadline = time.monotonic() + max(1.0, min(timeout, 110.0))
    while time.monotonic() < deadline:
        st = store.get_answer_state(session_id)
        if st["answered"]:
            return {"answered": True, "correct": bool(st["correct"])}
        await asyncio.sleep(0.5)
    return {"answered": False, "correct": None}
