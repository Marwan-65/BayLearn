"""
backend.py
==========
Adaptive Learning backend.

Endpoints:
    POST /session/start      — frontend triggers a new session
    GET  /session/status     — frontend polls for progress
    GET  /student/level      — returns student's current global APR

Swagger UI: http://localhost:8000/docs

Both DBs use UUIDs. The same user UUID and course UUID work in both DBs.
Frontend always sends raw UUIDs — backend resolves names internally.

Required .env keys:
    CONCEPT_DB_URL
    CHUNK_DB_URL
    GROQ_API_KEY

Run:
    pip install flask flasgger psycopg2-binary sqlalchemy python-dotenv numpy
    python backend.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import requests
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flasgger import Swagger
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from db_models import ensure_tables

load_dotenv(Path(__file__).parent / ".env")

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Swagger
# ---------------------------------------------------------------------------
swagger_config = {
    "headers": [],
    "specs": [{"endpoint": "apispec", "route": "/apispec.json",
                "rule_filter": lambda rule: True,
                "model_filter": lambda tag: True}],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/docs",
}
swagger_template = {
    "swagger": "2.0",
    "info": {
        "title":       "BayLearn Adaptive Learning API",
        "description": "Adaptive session orchestration.",
        "version":     "1.0.0",
    },
    "basePath": "/",
    "schemes":  ["http", "https"],
    "consumes": ["application/json"],
    "produces": ["application/json"],
    "tags": [
        {"name": "Session", "description": "Adaptive session management"},
        {"name": "Student", "description": "Student knowledge level"},
    ],
    "definitions": {
        "SessionStartRequest": {
            "type": "object",
            "required": ["user_id", "scope_ids"],
            "properties": {
                "user_id": {
                    "type": "string",
                    "example": "550e8400-e29b-41d4-a716-446655440000",
                    "description": "Chunk DB user UUID",
                },
                "scope_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "example": ["550e8400-e29b-41d4-a716-446655440001"],
                    "description": "File UUIDs from the chunk DB.",
                },
                "question_type": {
                    "type": "string",
                    "enum": ["mcq", "true_false", "short_answer"],
                    "example": "mcq",
                    "default": "mcq",
                    "description": "Question format passed to the question generation module.",
                },
            },
        },
        "SessionStartResponse": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "status":     {"type": "string", "example": "started"},
                "scope_ids":  {"type": "array", "items": {"type": "string"}},
                "prior_apr":  {"type": "number", "format": "float"},
                "question_type": {"type": "string", "example": "mcq"},
                "message":    {"type": "string"},
            },
        },
        "SessionStatusResponse": {
            "type": "object",
            "properties": {
                "session_id":   {"type": "string"},
                "user_id":      {"type": "string"},
                "scope_ids":    {"type": "string"},
                "started_at":   {"type": "string"},
                "ended_at":     {"type": "string"},
                "finished":     {"type": "boolean"},
                "steps_so_far": {"type": "integer"},
                "final_apr":    {"type": "number"},
            },
        },
        "StudentLevelResponse": {
            "type": "object",
            "properties": {
                "user_id":     {"type": "string"},
                "global_apr":  {"type": "number"},
                "has_history": {"type": "boolean"},
            },
        },
        "ErrorResponse": {
            "type": "object",
            "properties": {"error": {"type": "string"}},
        },
        "SessionTerminateRequest": {
            "type": "object",
            "required": ["session_id"],
            "properties": {
                "session_id": {
                    "type": "string",
                    "example": "550e8400-e29b-41d4-a716-446655440002",
                },
            },
        },
    },
}
swagger = Swagger(app, config=swagger_config, template=swagger_template)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
ALLOWED_ORIGINS = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
}
ALLOWED_HEADERS = {
    "Accept",
    "Content-Type",
    "Authorization",
    "X-Requested-With",
}


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin")
    if origin in ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, DELETE"
        response.headers["Access-Control-Allow-Headers"] = ", ".join(sorted(ALLOWED_HEADERS))
        response.headers["Access-Control-Max-Age"] = "86400"
    return response

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CONCEPT_DB_URL        = os.environ.get("CONCEPT_DB_URL",        "").strip()
CHUNK_DB_URL          = os.environ.get("CHUNK_DB_URL",          "").strip()
QUESTION_GEN_BASE_URL = os.environ.get("QUESTION_GEN_BASE_URL", "http://localhost:8001").strip()
EPPO_SCRIPT           = Path(__file__).parent / "eppo_inference.py"

if not CONCEPT_DB_URL:
    print("ERROR: CONCEPT_DB_URL not set in .env", file=sys.stderr); sys.exit(1)
if not CHUNK_DB_URL:
    print("ERROR: CHUNK_DB_URL not set in .env",   file=sys.stderr); sys.exit(1)
if not QUESTION_GEN_BASE_URL:
    print("ERROR: QUESTION_GEN_BASE_URL not set in .env", file=sys.stderr); sys.exit(1)


# ---------------------------------------------------------------------------
# Chunk DB helpers
# ---------------------------------------------------------------------------

def _chunk_engine():
    return create_engine(CHUNK_DB_URL)


def get_course_info_for_files(file_uuids: list[str]) -> dict | None:
    """
    Return {id, name} of the course these files belong to.
    Returns None if files are uncategorized.
    """
    from sqlalchemy import bindparam, ARRAY
    from sqlalchemy.dialects.postgresql import UUID as PG_UUID
    with Session(_chunk_engine()) as session:
        row = session.execute(
            text("""
                SELECT co.id::text, co.name
                FROM   uploaded_files uf
                JOIN   courses co ON co.id = uf.course_id
                WHERE  uf.id = ANY(:ids)
                  AND  uf.course_id IS NOT NULL
                LIMIT  1
            """).bindparams(bindparam("ids", value=file_uuids,
                                        type_=ARRAY(PG_UUID))),
        ).fetchone()
    return {"id": row[0], "name": row[1]} if row else None


# ---------------------------------------------------------------------------
# Concept DB helpers
# ---------------------------------------------------------------------------

def _concept_engine():
    return create_engine(CONCEPT_DB_URL)


def get_unextracted_files(file_uuids: list[str]) -> list[str]:
    """
    Core check used by both scope modes.
    Returns file UUIDs that do NOT yet have any concepts in concept_files.
    A file is considered extracted if it has at least one row in concept_files.
    """
    if not file_uuids:
        return []
    with Session(_concept_engine()) as session:
        try:
            rows = session.execute(text("""
                SELECT DISTINCT file_id FROM concept_files
                WHERE file_id = ANY(:ids)
            """), {"ids": file_uuids}).fetchall()
            already_extracted = {row[0] for row in rows}
        except Exception:
            already_extracted = set()
    return [fid for fid in file_uuids if fid not in already_extracted]


def create_session_row(user_id: str, scope_ids: str) -> str:
    """Insert a session row, return its UUID."""
    import uuid
    session_uuid = str(uuid.uuid4())
    with Session(_concept_engine()) as session:
        session.execute(text("""
            INSERT INTO sessions (id, user_id, scope_ids, started_at)
            VALUES (:sid, :uid, :si, NOW())
        """), {"sid": session_uuid, "uid": user_id, "si": scope_ids})
        session.commit()
    return session_uuid


def get_session_row(session_id: str) -> dict | None:
    with Session(_concept_engine()) as session:
        row = session.execute(text("""
            SELECT id, user_id, scope_ids,
                   started_at, ended_at, result_json
            FROM sessions WHERE id = :sid
        """), {"sid": session_id}).fetchone()
    if row is None:
        return None
    return {
        "session_id":  row[0],
        "user_id":     row[1],
        "scope_ids":   row[2],
        "started_at":  row[3].isoformat() if row[3] else None,
        "ended_at":    row[4].isoformat() if row[4] else None,
        "finished":    row[4] is not None,
        "result_json": row[5],
    }


def get_student_apr(user_id: str) -> float | None:
    with Session(_concept_engine()) as session:
        rows = session.execute(text("""
            SELECT sps.succ_hard, sps.fail_hard, sps.bonus_hard, c.difficulty
            FROM student_pfa_state sps
            JOIN concepts c ON c.id = sps.concept_id
            WHERE sps.user_id = :uid
        """), {"uid": user_id}).fetchall()
    if not rows:
        return None
    GAMMA = 0.8884; RHO = 0.2331; BETA_L = 0.4271
    LLM_BETA_SCALE = -0.4; LLM_BETA_MID = 3.0
    probs = []
    for (sh, fh, bh, diff) in rows:
        z = ((diff - LLM_BETA_MID) * LLM_BETA_SCALE + BETA_L
             + GAMMA * np.log1p(sh) - RHO * np.log1p(fh) + bh)
        probs.append(float(1.0 / (1.0 + np.exp(-np.clip(z, -15, 15)))))
    return float(np.mean(probs))


def run_concept_extractor(file_ids: list[str], course_id: str,
                           course_name: str, user_id: str) -> None:
    from concept_extractor import extract_and_store
    result = extract_and_store(
        file_ids=file_ids,
        course_id=course_id,
        course_name=course_name,
        user_id=user_id,
    )
    print(f"[backend] Extraction result: {result}")


def call_config_endpoint(session_id: str, file_ids: list[str],
                          question_type: str) -> None:
    """
    Call POST /api/v1/questions/adaptive/{session_id}/config on the
    question generation module to register file IDs and question type
    for this session before eppo starts sending generate requests.
    """
    url = (f"{QUESTION_GEN_BASE_URL}"
           f"/api/v1/questions/adaptive/{session_id}/config")
    try:
        resp = requests.post(url, json={
            "file_ids":",".join(file_ids),
            "question_type": question_type,
        }, timeout=10)
        resp.raise_for_status()
        print(f"[backend] Config sent to question module: {resp.json()}")
    except Exception as e:
        print(f"[backend] WARNING: config call failed: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# POST /session/start
# ---------------------------------------------------------------------------

@app.route("/session/start", methods=["POST"])
def start_session():
    """
    Start a new adaptive learning session.
    ---
    tags:
      - Session
    parameters:
      - in: body
        name: body
        required: true
        schema:
          $ref: '#/definitions/SessionStartRequest'
    responses:
      200:
        description: Session created and inference process launched.
        schema:
          $ref: '#/definitions/SessionStartResponse'
      400:
        description: Missing or invalid parameters.
        schema:
          $ref: '#/definitions/ErrorResponse'
      404:
        description: Course or file not found.
        schema:
          $ref: '#/definitions/ErrorResponse'
      422:
        description: Course has no concepts yet.
        schema:
          $ref: '#/definitions/ErrorResponse'
    """
    data = request.get_json(force=True)

    data = request.get_json(force=True)

    user_id       = data.get("user_id")           # chunk DB user UUID
    file_ids      = data.get("scope_ids", [])     # chunk DB file UUIDs
    question_type = data.get("question_type", "mcq")

    if not user_id:
        return jsonify({"error": "user_id is required"}), 400

    if isinstance(file_ids, str):
        file_ids = [v.strip() for v in file_ids.split(",") if v.strip()]

    if not file_ids:
        return jsonify({"error": "scope_ids (file UUIDs) must not be empty"}), 400

    if question_type not in ("mcq", "true_false", "short_answer"):
        return jsonify({
            "error": "question_type must be mcq, true_false, or short_answer"
        }), 400

    scope_ids_str = ",".join(file_ids)

    # ── Step 1: extract concepts for any files not yet processed ────────
    missing_file_ids = get_unextracted_files(file_ids)
    if missing_file_ids:
        course_info = get_course_info_for_files(missing_file_ids)
        if course_info:
            course_id   = course_info["id"]
            course_name = course_info["name"]
        else:
            course_id   = None
            course_name = "uncategorized"
        print(f"[backend] {len(missing_file_ids)} file(s) need extraction "
              f"(course='{course_name}')...")
        run_concept_extractor(missing_file_ids, course_id,
                              course_name, user_id)
    else:
        print(f"[backend] All {len(file_ids)} files already extracted.")

    # ── Step 2: create session row ──────────────────────────────────────
    session_id = create_session_row(user_id, scope_ids_str)
    print(f"[backend] Created session {session_id} for user {user_id[:8]}...")

    # ── Step 3: configure the question generation module ────────────────
    # Must happen before eppo starts — eppo POSTs /generate on its first step
    call_config_endpoint(session_id, file_ids, question_type)

    # ── Step 4: launch eppo_inference.py ───────────────────────────────
    cmd = [
        sys.executable, str(EPPO_SCRIPT),
        "--user-id",       user_id,
        "--session-id",    session_id,
        "--scope-ids",     scope_ids_str,
    ]
    subprocess.Popen(cmd)
    print(f"[backend] Launched eppo_inference for session {session_id[:8]}...")

    prior_apr = get_student_apr(user_id)
    return jsonify({
        "session_id":    session_id,
        "status":        "started",
        "scope_ids":     file_ids,
        "question_type": question_type,
        "prior_apr":     round(prior_apr, 4) if prior_apr is not None else None,
        "message":       "Session started. Poll /session/status for progress.",
    }), 200


# ---------------------------------------------------------------------------
# GET /session/status
# ---------------------------------------------------------------------------

@app.route("/session/status", methods=["GET"])
def session_status():
    """
    Poll the status of a running or finished session.
    ---
    tags:
      - Session
    parameters:
      - in: query
        name: session_id
        type: string
        required: true
        example: "550e8400-e29b-41d4-a716-446655440002"
    responses:
      200:
        description: Session status.
        schema:
          $ref: '#/definitions/SessionStatusResponse'
      400:
        description: Missing session_id.
        schema:
          $ref: '#/definitions/ErrorResponse'
      404:
        description: Session not found.
        schema:
          $ref: '#/definitions/ErrorResponse'
    """
    session_id = request.args.get("session_id")
    if not session_id:
        return jsonify({"error": "session_id is required"}), 400

    row = get_session_row(session_id)
    if row is None:
        return jsonify({"error": "session not found"}), 404

    with Session(_concept_engine()) as session:
        steps = session.execute(text("""
            SELECT COUNT(*) FROM session_interactions
            WHERE session_id = :sid
        """), {"sid": session_id}).scalar()

    row["steps_so_far"] = steps
    if row["finished"]:
        row["final_apr"] = get_student_apr(row["user_id"])
        # Include structured results if available
        if row.get("result_json"):
            import json as _json
            try:
                row["results"] = _json.loads(row["result_json"])
            except Exception:
                pass
    row.pop("result_json", None)   # don't expose raw JSON string

    return jsonify(row), 200


# ---------------------------------------------------------------------------
# POST /session/terminate
# ---------------------------------------------------------------------------

@app.route("/session/terminate", methods=["POST", "OPTIONS"])
def terminate_session():
    """
    Request early termination of a running session.
    Sets terminate_requested=true in the DB; eppo_inference picks it up
    within one long-poll cycle (≤55 s) and saves PFA state before exiting.
    ---
    tags:
      - Session
    parameters:
      - in: body
        name: body
        required: true
        schema:
          $ref: '#/definitions/SessionTerminateRequest'
    responses:
      200:
        description: Termination flag set. Poll /session/status for finished=true.
      400:
        description: Missing session_id.
        schema:
          $ref: '#/definitions/ErrorResponse'
      404:
        description: Session not found or already finished.
        schema:
          $ref: '#/definitions/ErrorResponse'
    """
    if request.method == "OPTIONS":
        return "", 204

    data = request.get_json(force=True) or {}
    session_id = data.get("session_id")
    if not session_id:
        return jsonify({"error": "session_id is required"}), 400

    row = get_session_row(session_id)
    if row is None:
        return jsonify({"error": "session not found"}), 404
    if row["finished"]:
        return jsonify({"error": "session already finished"}), 404

    with Session(_concept_engine()) as session:
        session.execute(text("""
            UPDATE sessions SET terminate_requested = TRUE WHERE id = :sid
        """), {"sid": session_id})
        session.commit()

    print(f"[backend] Termination requested for session {session_id[:8]}...")
    return jsonify({
        "status":  "terminating",
        "message": "Termination flag set. Poll /session/status for finished=true.",
    }), 200


# ---------------------------------------------------------------------------
# GET /session/results
# ---------------------------------------------------------------------------

@app.route("/session/results", methods=["GET"])
def session_results():
    """
    Get the full results and learning insights for a finished session.
    The frontend calls this at session end to show the progress card.
    ---
    tags:
      - Session
    parameters:
      - in: query
        name: session_id
        type: string
        required: true
        example: "550e8400-e29b-41d4-a716-446655440002"
    responses:
      200:
        description: Session results with human-readable messages and insights.
      400:
        description: Missing session_id.
      404:
        description: Session not found or not finished yet.
    """
    import json as _json
    import numpy as np

    session_id = request.args.get("session_id")
    if not session_id:
        return jsonify({"error": "session_id is required"}), 400

    row = get_session_row(session_id)
    if row is None:
        return jsonify({"error": "session not found"}), 404
    if not row["finished"]:
        return jsonify({"error": "session not finished yet"}), 404

    # ── Parse raw result from eppo ─────────────────────────────────────
    raw = {}
    if row.get("result_json"):
        try:
            raw = _json.loads(row["result_json"])
        except Exception:
            pass

    apr_start  = raw.get("apr_start",      0.0)
    apr_final  = raw.get("apr_final",      0.0)
    global_apr = raw.get("global_apr",     0.0)
    wapr_final = raw.get("wapr_final",     0.0)
    wapr_start = raw.get("wapr_start",     apr_start)
    wapr_target= raw.get("wapr_target",    wapr_final)
    goal_met   = raw.get("goal_met",       False)
    steps      = raw.get("steps",          0)
    n_mastered = raw.get("newly_mastered", 0)
    apr_per    = raw.get("apr_per_course", {})

    # ── Goal progress ─────────────────────────────────────────────────
    goal_range        = wapr_target - wapr_start
    goal_achieved_pct = (
        round(min((wapr_final - wapr_start) / goal_range * 100, 100), 1)
        if goal_range > 1e-6 else 100.0
    )
    target_improvement_pct = round((wapr_target - wapr_start) * 100, 1)
    actual_improvement_pct = round((wapr_final  - wapr_start) * 100, 1)

    # ── Level label ───────────────────────────────────────────────────
    def _level_label(apr: float) -> str:
        if apr >= 0.85: return "Advanced"
        if apr >= 0.70: return "Proficient"
        if apr >= 0.55: return "Developing"
        if apr >= 0.40: return "Beginner"
        return "Novice"

    level = _level_label(global_apr)

    # ── Concept breakdown from PFA state ──────────────────────────────
    GAMMA = 0.8884; RHO = 0.2331; BETA_L = 0.4271
    LLM_BETA_SCALE = -0.4; LLM_BETA_MID = 3.0

    with Session(_concept_engine()) as db:
        concept_rows = db.execute(text("""
            SELECT c.name, sps.succ_hard, sps.fail_hard,
                   sps.bonus_hard, c.difficulty
            FROM   student_pfa_state sps
            JOIN   concepts c ON c.id = sps.concept_id
            JOIN   concept_files cf ON cf.concept_id = c.id
            WHERE  sps.user_id = :uid
              AND  cf.file_id  = ANY(string_to_array(:scope, ','))
        """), {
            "uid":   row["user_id"],
            "scope": row["scope_ids"],
        }).fetchall()

    concept_probs = []
    for (name, sh, fh, bh, diff) in concept_rows:
        z = ((diff - LLM_BETA_MID) * LLM_BETA_SCALE + BETA_L
             + GAMMA * np.log1p(sh) - RHO * np.log1p(fh) + bh)
        p = float(1.0 / (1.0 + np.exp(-np.clip(z, -15, 15))))
        concept_probs.append({"name": name, "p_hard": round(p, 3)})

    concept_probs.sort(key=lambda x: x["p_hard"], reverse=True)
    strongest = concept_probs[:3]
    weakest   = concept_probs[-3:][::-1] if len(concept_probs) >= 3                 else concept_probs[::-1]
    focus_concept = weakest[0]["name"] if weakest else None

    # ── Human-readable messages ───────────────────────────────────────
    # Goal description — what the session was trying to achieve
    goal_description = (
        f"Improve your mastery of these concepts by "
        f"{target_improvement_pct}% during this session."
    )

    # Progress summary — what actually happened
    if goal_met:
        progress_summary = (
            f"Great work! You achieved {goal_achieved_pct}% of your session "
            f"goal and answered {steps} questions."
        )
    elif goal_achieved_pct >= 75:
        progress_summary = (
            f"Almost there — you achieved {goal_achieved_pct}% of your "
            f"session goal across {steps} questions. Keep going!"
        )
    elif goal_achieved_pct >= 40:
        progress_summary = (
            f"You achieved {goal_achieved_pct}% of your session goal "
            f"across {steps} questions. More practice will get you there."
        )
    else:
        progress_summary = (
            f"You achieved {goal_achieved_pct}% of your session goal "
            f"across {steps} questions. This material needs more attention."
        )

    # Mastery message
    if n_mastered > 0:
        mastery_message = (
            f"You mastered {n_mastered} new concept"
            f"{'s' if n_mastered > 1 else ''} this session!"
        )
    else:
        mastery_message = None

    # Next step recommendation
    if focus_concept:
        if goal_met:
            next_step = (
                f"You're on a roll! Try a new session focusing on "
                f'"{focus_concept}" to keep building.'
            )
        else:
            next_step = (
                f'Focus on "{focus_concept}" in your next session — '
                f"it's your weakest concept right now."
            )
    else:
        next_step = "Start a new session to keep improving."

    # Level message
    level_message = (
        f"Your overall knowledge level is {level} "
        f"({round(global_apr * 100, 1)}% mastery across all studied concepts)."
    )

    return jsonify({
        # ── Human-readable (ready to display directly) ─────────────────
        "goal_description":  goal_description,
        "progress_summary":  progress_summary,
        "mastery_message":   mastery_message,
        "next_step":         next_step,
        "level_message":     level_message,

        # ── Goal ───────────────────────────────────────────────────────
        "goal_met":              goal_met,
        "goal_achieved_pct":     goal_achieved_pct,
        "target_improvement_pct": target_improvement_pct,
        "actual_improvement_pct": actual_improvement_pct,

        # ── Session numbers ────────────────────────────────────────────
        "steps_taken":       steps,
        "concepts_mastered": n_mastered,

        # ── Knowledge level ────────────────────────────────────────────
        "global_apr": round(global_apr, 4),
        "level":      level,

        # ── Per-course breakdown ───────────────────────────────────────
        "apr_per_course": {
            course: round(apr, 4)
            for course, apr in apr_per.items()
        },

        # ── Concept insights ───────────────────────────────────────────
        "strongest_concepts":  strongest,
        "weakest_concepts":    weakest,
        "next_session_focus":  focus_concept,
    }), 200


# ---------------------------------------------------------------------------
# GET /student/level
# ---------------------------------------------------------------------------

@app.route("/student/level", methods=["GET"])
def student_level():
    """
    Get a student's current global knowledge level (APR).
    ---
    tags:
      - Student
    parameters:
      - in: query
        name: user_id
        type: string
        required: true
        description: Chunk DB user UUID
        example: "550e8400-e29b-41d4-a716-446655440000"
    responses:
      200:
        description: Student's global APR.
        schema:
          $ref: '#/definitions/StudentLevelResponse'
      400:
        description: Missing user_id.
        schema:
          $ref: '#/definitions/ErrorResponse'
    """
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400
    apr = get_student_apr(user_id)
    return jsonify({
        "user_id":     user_id,
        "global_apr":  round(apr, 4) if apr is not None else None,
        "has_history": apr is not None,
    }), 200


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """
    Health check.
    ---
    tags:
      - Session
    responses:
      200:
        description: Server is running.
    """
    return jsonify({
        "status": "BayLearn adaptive backend running",
        "docs":   request.host_url + "docs",
    }), 200


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ensure_tables(CONCEPT_DB_URL)
    print("BayLearn adaptive backend — http://localhost:8002")
    print("Swagger UI             — http://localhost:8002/docs")
    app.run(host="0.0.0.0", port=8002, debug=False)