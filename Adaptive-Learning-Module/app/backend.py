"""
backend.py
==========
Adaptive Learning backend.

Endpoints:
    POST /session/start      — frontend triggers a new session
    GET  /session/status     — frontend polls for progress
    GET  /student/level      — returns student's current global APR

Swagger UI available at:
    http://localhost:8000/docs

Required .env keys:
    CONCEPT_DB_URL
    CHUNK_DB_URL
    GROQ_API_KEY

Run:
    pip install flask flasgger psycopg2-binary sqlalchemy python-dotenv
    python backend.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flasgger import Swagger, swag_from
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

load_dotenv(Path(__file__).parent / ".env")

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Swagger config
# ---------------------------------------------------------------------------
swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": "apispec",
            "route":    "/apispec.json",
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/docs",
}

swagger_template = {
    "swagger": "2.0",
    "info": {
        "title":       "BayLearn Adaptive Learning API",
        "description": "Adaptive session orchestration for the BayLearn platform.",
        "version":     "1.0.0",
        "contact":     {"email": "team@baylearn.com"},
    },
    "basePath": "/",
    "schemes":  ["http", "https"],
    "consumes": ["application/json"],
    "produces": ["application/json"],
    "tags": [
        {"name": "Session",  "description": "Adaptive session management"},
        {"name": "Student",  "description": "Student knowledge level"},
    ],
    "definitions": {
        "SessionStartRequest": {
            "type": "object",
            "required": ["user_id", "scope_type", "scope_value"],
            "properties": {
                "user_id": {
                    "type": "integer",
                    "example": 3,
                    "description": "ID of the student starting the session",
                },
                "scope_type": {
                    "type": "string",
                    "enum": ["course", "files"],
                    "example": "course",
                    "description": (
                        "'course' — study one or more full courses. "
                        "'files' — study specific uploaded files."
                    ),
                },
                "scope_value": {
                    "type": "array",
                    "items": {"type": "string"},
                    "example": ["algorithms", "data structures"],
                    "description": (
                        "List of course names (scope_type=course) "
                        "or file UUIDs (scope_type=files)."
                    ),
                },
                "course_name": {
                    "type": "string",
                    "example": "Algorithms",
                    "description": (
                        "Required only when scope_type='files'. "
                        "The course these files belong to."
                    ),
                },
            },
        },
        "SessionStartResponse": {
            "type": "object",
            "properties": {
                "session_id":  {"type": "integer",  "example": 47},
                "status":      {"type": "string",   "example": "started"},
                "scope_type":  {"type": "string",   "example": "course"},
                "scope_value": {
                    "type": "array",
                    "items": {"type": "string"},
                    "example": ["algorithms"],
                },
                "prior_apr": {
                    "type": "number", "format": "float",
                    "example": 0.6122,
                    "description": (
                        "Student's global APR before this session. "
                        "null if no history exists yet."
                    ),
                },
                "message": {"type": "string"},
            },
        },
        "SessionStatusResponse": {
            "type": "object",
            "properties": {
                "session_id":   {"type": "integer", "example": 47},
                "user_id":      {"type": "integer", "example": 3},
                "scope_type":   {"type": "string",  "example": "course"},
                "scope_value":  {"type": "string",  "example": "algorithms"},
                "started_at":   {"type": "string",  "example": "2026-05-29T10:00:00"},
                "ended_at": {
                    "type": "string", "example": "2026-05-29T10:20:00",
                    "description": "null while session is still running",
                },
                "finished":      {"type": "boolean", "example": False},
                "steps_so_far":  {"type": "integer", "example": 12},
                "final_apr": {
                    "type": "number", "format": "float",
                    "example": 0.7341,
                    "description": "Only present when finished=true",
                },
            },
        },
        "StudentLevelResponse": {
            "type": "object",
            "properties": {
                "user_id":     {"type": "integer", "example": 3},
                "global_apr": {
                    "type": "number", "format": "float",
                    "example": 0.6834,
                    "description": (
                        "Average P(correct|Hard) across all concepts "
                        "in the student's history. null if no history yet."
                    ),
                },
                "has_history": {"type": "boolean", "example": True},
            },
        },
        "ErrorResponse": {
            "type": "object",
            "properties": {
                "error": {"type": "string", "example": "user_id is required"},
            },
        },
    },
}

swagger = Swagger(app, config=swagger_config, template=swagger_template)

CONCEPT_DB_URL = os.environ.get("CONCEPT_DB_URL", "").strip()
EPPO_SCRIPT    = Path(__file__).parent / "eppo_inference.py"

if not CONCEPT_DB_URL:
    print("ERROR: CONCEPT_DB_URL not set in .env", file=sys.stderr)
    sys.exit(1)
def ensure_tables() -> None:
    engine = create_engine(CONCEPT_DB_URL)
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sessions (
                id          SERIAL PRIMARY KEY,
                user_id     INTEGER NOT NULL,
                scope_type  VARCHAR,
                scope_value VARCHAR,
                started_at  TIMESTAMP NOT NULL DEFAULT NOW(),
                ended_at    TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS student_pfa_state (
                user_id    INTEGER NOT NULL,
                concept_id INTEGER NOT NULL,
                succ_easy  FLOAT NOT NULL DEFAULT 0,
                succ_med   FLOAT NOT NULL DEFAULT 0,
                succ_hard  FLOAT NOT NULL DEFAULT 0,
                fail_easy  FLOAT NOT NULL DEFAULT 0,
                fail_med   FLOAT NOT NULL DEFAULT 0,
                fail_hard  FLOAT NOT NULL DEFAULT 0,
                bonus_easy FLOAT NOT NULL DEFAULT 0,
                bonus_med  FLOAT NOT NULL DEFAULT 0,
                bonus_hard FLOAT NOT NULL DEFAULT 0,
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                PRIMARY KEY (user_id, concept_id)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS session_interactions (
                id           SERIAL PRIMARY KEY,
                session_id   INTEGER NOT NULL,
                user_id      INTEGER NOT NULL,
                concept_id   INTEGER NOT NULL,
                difficulty   VARCHAR(10) NOT NULL,
                correct      BOOLEAN NOT NULL,
                p_before     FLOAT NOT NULL,
                p_after      FLOAT NOT NULL,
                p_hard_after FLOAT NOT NULL,
                created_at   TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS concept_files (
                concept_id INTEGER NOT NULL,
                file_id    VARCHAR NOT NULL,
                PRIMARY KEY (concept_id, file_id)
            )
        """))
        conn.commit()
    print("[db] Tables verified.")


# run once at startup before any request
ensure_tables()

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _engine():
    return create_engine(CONCEPT_DB_URL)


def concepts_exist_for_files(file_ids: list[str]) -> bool:
    with Session(_engine()) as session:
        try:
            count = session.execute(text("""
                SELECT COUNT(*) FROM concept_files
                WHERE file_id = ANY(:ids)
            """), {"ids": file_ids}).scalar()
            return (count or 0) > 0
        except Exception:
            return False


def concepts_exist_for_course(course_name: str) -> bool:
    with Session(_engine()) as session:
        count = session.execute(text("""
            SELECT COUNT(*) FROM concepts c
            JOIN courses co ON co.id = c.course_id
            WHERE LOWER(REPLACE(co.name, '_', ' ')) = LOWER(:name)
        """), {"name": course_name.replace("_", " ")}).scalar()
        return (count or 0) > 0


def create_session_row(user_id: int, scope_type: str,
                       scope_value: str) -> int:
    with Session(_engine()) as session:
        result = session.execute(text("""
            INSERT INTO sessions (user_id, scope_type, scope_value, started_at)
            VALUES (:uid, :st, :sv, NOW())
            RETURNING id
        """), {"uid": user_id, "st": scope_type, "sv": scope_value})
        session.commit()
        return result.scalar()


def get_session_row(session_id: int) -> dict | None:
    with Session(_engine()) as session:
        row = session.execute(text("""
            SELECT id, user_id, scope_type, scope_value,
                   started_at, ended_at
            FROM sessions WHERE id = :sid
        """), {"sid": session_id}).fetchone()
    if row is None:
        return None
    return {
        "session_id":  row[0],
        "user_id":     row[1],
        "scope_type":  row[2],
        "scope_value": row[3],
        "started_at":  row[4].isoformat() if row[4] else None,
        "ended_at":    row[5].isoformat() if row[5] else None,
        "finished":    row[5] is not None,
    }


def get_student_apr(user_id: int) -> float | None:
    with Session(_engine()) as session:
        rows = session.execute(text("""
            SELECT sps.succ_hard, sps.fail_hard, sps.bonus_hard, c.difficulty
            FROM student_pfa_state sps
            JOIN concepts c ON c.id = sps.concept_id
            WHERE sps.user_id = :uid
        """), {"uid": user_id}).fetchall()

    if not rows:
        return None

    GAMMA  = 0.8884
    RHO    = 0.2331
    BETA_L = 0.4271
    LLM_BETA_SCALE = -0.4
    LLM_BETA_MID   = 3.0

    probs = []
    for (sh, fh, bh, diff) in rows:
        beta_c = (diff - LLM_BETA_MID) * LLM_BETA_SCALE
        z = (beta_c + BETA_L
             + GAMMA * np.log1p(sh)
             - RHO   * np.log1p(fh)
             + bh)
        probs.append(float(1.0 / (1.0 + np.exp(-np.clip(z, -15, 15)))))

    return float(np.mean(probs))


def run_concept_extractor(file_ids: list[str], course_name: str,
                           user_id: int) -> None:
    from concept_extractor import extract_and_store
    result = extract_and_store(
        file_ids=file_ids,
        course_name=course_name,
        user_id=user_id,
    )
    print(f"[backend] Extraction result: {result}")


# ---------------------------------------------------------------------------
# POST /session/start
# ---------------------------------------------------------------------------

@app.route("/session/start", methods=["POST"])
def start_session():
    """
    Start a new adaptive learning session for a student.
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
      422:
        description: >
          Courses selected have no concepts yet.
          Upload and process their files first via the Input-Parsing module.
        schema:
          type: object
          properties:
            error:
              type: string
            missing_courses:
              type: array
              items:
                type: string
              example: ["algorithms"]
    """
    data = request.get_json(force=True)

    user_id     = data.get("user_id")
    scope_type  = data.get("scope_type", "course")
    scope_value = data.get("scope_value", "")
    course_name = data.get("course_name", "")

    if not user_id:
        return jsonify({"error": "user_id is required"}), 400

    if isinstance(scope_value, list):
        values = [str(v).strip() for v in scope_value if str(v).strip()]
    else:
        values = [v.strip() for v in str(scope_value).split(",") if v.strip()]

    if not values:
        return jsonify({"error": "scope_value must not be empty"}), 400

    scope_value_str = ",".join(values)

    if scope_type == "files":
        if not course_name:
            return jsonify({
                "error": "course_name is required for files scope"
            }), 400
        missing = [fid for fid in values
                   if not concepts_exist_for_files([fid])]
        if missing:
            print(f"[backend] Extracting concepts for "
                  f"{len(missing)} files in '{course_name}'...")
            run_concept_extractor(missing, course_name, user_id)
        else:
            print(f"[backend] All {len(values)} files already have concepts.")

    elif scope_type == "course":
        missing = [c for c in values if not concepts_exist_for_course(c)]
        if missing:
            return jsonify({
                "error": "The following courses have no concepts yet. "
                         "Upload and process their files first.",
                "missing_courses": missing,
            }), 422
        print(f"[backend] All {len(values)} courses have concepts.")

    else:
        return jsonify({"error": f"Unknown scope_type '{scope_type}'"}), 400

    session_id = create_session_row(user_id, scope_type, scope_value_str)
    print(f"[backend] Created session {session_id} for user {user_id}.")

    cmd = [
        sys.executable, str(EPPO_SCRIPT),
        "--user-id",     str(user_id),
        "--session-id",  str(session_id),
        "--scope-type",  scope_type,
        "--scope-value", scope_value_str,
    ]
    subprocess.Popen(cmd)
    print(f"[backend] Launched eppo_inference for session {session_id}.")

    prior_apr = get_student_apr(user_id)
    return jsonify({
        "session_id":  session_id,
        "status":      "started",
        "scope_type":  scope_type,
        "scope_value": values,
        "prior_apr":   round(prior_apr, 4) if prior_apr is not None else None,
        "message":     "Session started. Poll /session/status for progress.",
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
        type: integer
        required: true
        description: The session ID returned by POST /session/start
        example: 47
    responses:
      200:
        description: Session status and step count.
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
    session_id = request.args.get("session_id", type=int)
    if not session_id:
        return jsonify({"error": "session_id is required"}), 400

    row = get_session_row(session_id)
    if row is None:
        return jsonify({"error": "session not found"}), 404

    with Session(_engine()) as session:
        steps = session.execute(text("""
            SELECT COUNT(*) FROM session_interactions
            WHERE session_id = :sid
        """), {"sid": session_id}).scalar()

    row["steps_so_far"] = steps

    if row["finished"]:
        row["final_apr"] = get_student_apr(row["user_id"])

    return jsonify(row), 200


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
        type: integer
        required: true
        description: The student's user ID
        example: 3
    responses:
      200:
        description: >
          Student's global APR computed from their full accumulated
          PFA history across all concepts. global_apr is null if the
          student has never completed a session.
        schema:
          $ref: '#/definitions/StudentLevelResponse'
      400:
        description: Missing user_id.
        schema:
          $ref: '#/definitions/ErrorResponse'
    """
    user_id = request.args.get("user_id", type=int)
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400

    apr = get_student_apr(user_id)
    return jsonify({
        "user_id":     user_id,
        "global_apr":  round(apr, 4) if apr is not None else None,
        "has_history": apr is not None,
    }), 200


# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """
    Health check and API entry point.
    ---
    tags:
      - Session
    responses:
      200:
        description: Server is running.
        schema:
          type: object
          properties:
            status:
              type: string
              example: running
            docs:
              type: string
              example: http://localhost:8000/docs
    """
    return jsonify({
        "status": "BayLearn adaptive backend running",
        "docs":   request.host_url + "docs",
    }), 200


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("BayLearn adaptive backend running on http://localhost:8000")
    print("Swagger UI available at  http://localhost:8000/docs")
    app.run(host="0.0.0.0", port=8000, debug=False)