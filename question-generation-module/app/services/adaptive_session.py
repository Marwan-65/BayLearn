"""
Adaptive-session coordination store.

Bridges the RL adaptive agent and the student's answers for the agent-driven
quiz loop:

    agent  POST /adaptive/{session}/generate  -> a question becomes "pending"
    frontend GET /adaptive/{session}/current   -> shows the pending question
    student POST /questions/check (session_id)  -> records correct/wrong
    agent  GET  /adaptive/{session}/answer      -> long-polls until answered

State is in-memory and keyed by session_id. For a single active student the
caller can just use a fixed session id (e.g. "default"), mirroring the mock's
single _last_question. A lock guards mutation; reads are cheap snapshots.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, Optional


class AdaptiveSessionStore:
    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _get(self, session_id: str) -> Dict[str, Any]:
        return self._sessions.setdefault(
            session_id,
            {
                "file_ids": None,        # which file(s) to generate from (set by frontend)
                "question_type": "mcq",
                "pending": None,         # the current question (card shape)
                "version": 0,            # increments each new question (frontend detects new)
                "answered": False,
                "is_correct": None,
                "score": None,
            },
        )

    def config(self, session_id: str, file_ids: str, question_type: Optional[str] = None) -> None:
        """Register which file(s) the agent's questions are generated from."""
        with self._lock:
            s = self._get(session_id)
            s["file_ids"] = file_ids
            if question_type:
                s["question_type"] = question_type

    def get_config(self, session_id: str) -> Dict[str, Any]:
        with self._lock:
            s = self._get(session_id)
            return {"file_ids": s["file_ids"], "question_type": s["question_type"]}

    def set_question(self, session_id: str, question: Dict[str, Any]) -> int:
        """Store a freshly generated question as pending; resets answer state."""
        with self._lock:
            s = self._get(session_id)
            s["pending"] = question
            s["version"] += 1
            s["answered"] = False
            s["is_correct"] = None
            s["score"] = None
            return s["version"]

    def get_current(self, session_id: str) -> Dict[str, Any]:
        """Frontend polls this to display the agent's current question."""
        with self._lock:
            s = self._get(session_id)
            return {
                "version": s["version"],
                "question": s["pending"],
                "answered": s["answered"],
            }

    def record_answer(self, session_id: str, is_correct: bool, score: Optional[float] = None) -> None:
        """Called when the student answers (via /questions/check)."""
        with self._lock:
            s = self._get(session_id)
            s["answered"] = True
            s["is_correct"] = bool(is_correct)
            s["score"] = score

    def get_answer_state(self, session_id: str) -> Dict[str, Any]:
        with self._lock:
            s = self._get(session_id)
            return {"answered": s["answered"], "correct": s["is_correct"], "score": s["score"]}
