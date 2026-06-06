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
                "file_ids": None,        # which file to generate from 
                "question_type": "mcq",
                "pending": None,         # the current question
                "version": 0,            # increments each new question
                "answered": False,
                "is_correct": None,
                "score": None,
            },
        )

    def config(self, session_id: str, file_ids: str, question_type: Optional[str] = None) -> None:
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
        with self._lock:
            s = self._get(session_id)
            s["pending"] = question
            s["version"] += 1
            s["answered"] = False
            s["is_correct"] = None
            s["score"] = None
            return s["version"]

    def get_current(self, session_id: str) -> Dict[str, Any]:
        with self._lock:
            s = self._get(session_id)
            return {
                "version": s["version"],
                "question": s["pending"],
                "answered": s["answered"],
            }

    def record_answer(self, session_id: str, is_correct: bool, score: Optional[float] = None) -> None:
        with self._lock:
            s = self._get(session_id)
            s["answered"] = True
            s["is_correct"] = bool(is_correct)
            s["score"] = score

    def get_answer_state(self, session_id: str) -> Dict[str, Any]:
        with self._lock:
            s = self._get(session_id)
            return {"answered": s["answered"], "correct": s["is_correct"], "score": s["score"]}
