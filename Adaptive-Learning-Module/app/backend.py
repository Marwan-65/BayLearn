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
            "required": ["user_id", "scope_type", "scope_ids"],
            "properties": {
                "user_id": {
                    "type": "string",
                    "example": "550e8400-e29b-41d4-a716-446655440000",
                    "description": "Chunk DB user UUID",
                },
                "scope_type": {
                    "type": "string",
                    "enum": ["course", "files"],
                    "example": "course",
                    "description": (
                        "'course' — list of chunk DB course UUIDs. "
                        "'files'  — list of chunk DB file UUIDs."
                    ),
                },
                "scope_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "example": ["550e8400-e29b-41d4-a716-446655440001"],
                    "description": "Course UUIDs or file UUIDs from chunk DB.",
                },
            },
        },
        "SessionStartResponse": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "status":     {"type": "string", "example": "started"},
                "scope_type": {"type": "string"},
                "scope_ids":  {"type": "array", "items": {"type": "string"}},
                "prior_apr":  {"type": "number", "format": "float"},
                "message":    {"type": "string"},
            },
        },
        "SessionStatusResponse": {
            "type": "object",
            "properties": {
                "session_id":   {"type": "string"},
                "user_id":      {"type": "string"},
                "scope_type":   {"type": "string"},
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
    },
}
swagger = Swagger(app, config=swagger_config, template=swagger_template)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CONCEPT_DB_URL = os.environ.get("CONCEPT_DB_URL", "").strip()
CHUNK_DB_URL   = os.environ.get("CHUNK_DB_URL",   "").strip()
EPPO_SCRIPT    = Path(__file__).parent / "eppo_inference.py"

if not CONCEPT_DB_URL:
    print("ERROR: CONCEPT_DB_URL not set in .env", file=sys.stderr); sys.exit(1)
if not CHUNK_DB_URL:
    print("ERROR: CHUNK_DB_URL not set in .env",   file=sys.stderr); sys.exit(1)


# ---------------------------------------------------------------------------
# Chunk DB helpers
# ---------------------------------------------------------------------------

def _chunk_engine():
    return create_engine(CHUNK_DB_URL)


def get_course_info(course_uuid: str) -> dict | None:
    """Return {id, name} for a chunk DB course UUID."""
    with Session(_chunk_engine()) as session:
        row = session.execute(text("""
            SELECT id::text, name FROM courses WHERE id = CAST(:id AS uuid)
        """), {"id": course_uuid}).fetchone()
    return {"id": row[0], "name": row[1]} if row else None


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


def get_file_ids_for_courses(course_uuids: list[str]) -> dict[str, list[str]]:
    """
    Fetch all file UUIDs for each course UUID from the chunk DB.
    Returns { course_uuid: [file_uuid, ...] }
    """
    from sqlalchemy import bindparam, ARRAY
    from sqlalchemy.dialects.postgresql import UUID as PG_UUID
    with Session(_chunk_engine()) as session:
        rows = session.execute(
            text("""
                SELECT course_id::text, id::text FROM uploaded_files
                WHERE course_id = ANY(:ids)
            """).bindparams(bindparam("ids", value=course_uuids,
                                        type_=ARRAY(PG_UUID))),
        ).fetchall()
    result: dict[str, list[str]] = {cid: [] for cid in course_uuids}
    for course_id, file_id in rows:
        result[course_id].append(file_id)
    return result


def create_session_row(user_id: str, scope_type: str,
                       scope_ids: str) -> str:
    """Insert a session row, return its UUID."""
    import uuid
    session_uuid = str(uuid.uuid4())
    with Session(_concept_engine()) as session:
        session.execute(text("""
            INSERT INTO sessions (id, user_id, scope_type, scope_ids, started_at)
            VALUES (:sid, :uid, :st, :si, NOW())
        """), {"sid": session_uuid, "uid": user_id,
               "st": scope_type,   "si": scope_ids})
        session.commit()
    return session_uuid


def get_session_row(session_id: str) -> dict | None:
    with Session(_concept_engine()) as session:
        row = session.execute(text("""
            SELECT id, user_id, scope_type, scope_ids,
                   started_at, ended_at
            FROM sessions WHERE id = :sid
        """), {"sid": session_id}).fetchone()
    if row is None:
        return None
    return {
        "session_id":  row[0],
        "user_id":     row[1],
        "scope_type":  row[2],
        "scope_ids":   row[3],
        "started_at":  row[4].isoformat() if row[4] else None,
        "ended_at":    row[5].isoformat() if row[5] else None,
        "finished":    row[5] is not None,
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

    user_id    = data.get("user_id")       # chunk DB user UUID
    scope_type = data.get("scope_type", "course")
    scope_ids  = data.get("scope_ids",  [])

    if not user_id:
        return jsonify({"error": "user_id is required"}), 400

    if isinstance(scope_ids, str):
        scope_ids = [v.strip() for v in scope_ids.split(",") if v.strip()]

    if not scope_ids:
        return jsonify({"error": "scope_ids must not be empty"}), 400

    scope_ids_str = ",".join(scope_ids)

    # ── Step 1: ensure concepts exist for all selected files/courses ──
    #
    # Core check for BOTH modes: does each file UUID have a row in concept_files?
    # This is the single source of truth — if a file has entries in concept_files
    # it has been extracted, regardless of scope mode.
    #
    # files mode  : scope_ids are file UUIDs → check directly
    # course mode : scope_ids are course UUIDs → resolve to file UUIDs first,
    #               then apply the same check per file

    if scope_type == "files":
        # Check each selected file individually
        missing_file_ids = get_unextracted_files(scope_ids)

        if missing_file_ids:
            # Resolve course info from chunk DB for the extractor
            course_info = get_course_info_for_files(missing_file_ids)
            if course_info:
                course_id   = course_info["id"]
                course_name = course_info["name"]
            else:
                # Uncategorized files — extractor generates a stable UUID
                course_id   = None
                course_name = "uncategorized"
            print(f"[backend] {len(missing_file_ids)} file(s) need extraction "
                  f"(course='{course_name}')...")
            run_concept_extractor(missing_file_ids, course_id,
                                  course_name, user_id)
        else:
            print(f"[backend] All {len(scope_ids)} files already extracted.")

    elif scope_type == "course":
        # Resolve all file UUIDs for the selected courses from chunk DB
        course_files = get_file_ids_for_courses(scope_ids)

        # Validate all courses exist in chunk DB
        for course_uuid in scope_ids:
            info = get_course_info(course_uuid)
            if info is None:
                return jsonify({
                    "error": f"Course UUID '{course_uuid}' not found in chunk DB."
                }), 404

        # Check each course: does it have files? are all files extracted?
        missing_courses = []   # courses with zero files uploaded
        for course_uuid in scope_ids:
            info       = get_course_info(course_uuid)
            course_name = info["name"]
            file_ids    = course_files.get(course_uuid, [])

            if not file_ids:
                # No files uploaded to this course yet — can't extract
                missing_courses.append({
                    "id":   course_uuid,
                    "name": course_name,
                    "reason": "no files uploaded",
                })
                continue

            # Check which files in this course aren't extracted yet
            missing_file_ids = get_unextracted_files(file_ids)
            if missing_file_ids:
                print(f"[backend] Course '{course_name}': "
                      f"{len(missing_file_ids)}/{len(file_ids)} file(s) "
                      f"need extraction...")
                run_concept_extractor(missing_file_ids, course_uuid,
                                      course_name, user_id)
            else:
                print(f"[backend] Course '{course_name}': "
                      f"all {len(file_ids)} file(s) already extracted.")

        if missing_courses:
            return jsonify({
                "error": "These courses have no uploaded files yet.",
                "missing_courses": missing_courses,
            }), 422

    else:
        return jsonify({"error": f"Unknown scope_type '{scope_type}'"}), 400

    # ── Step 2: create session row ──────────────────────────────────────
    session_id = create_session_row(user_id, scope_type, scope_ids_str)
    print(f"[backend] Created session {session_id} for user {user_id[:8]}...")

    # ── Step 3: launch eppo_inference.py ───────────────────────────────
    cmd = [
        sys.executable, str(EPPO_SCRIPT),
        "--user-id",    user_id,
        "--session-id", session_id,
        "--scope-type", scope_type,
        "--scope-ids",  scope_ids_str,
    ]
    subprocess.Popen(cmd)
    print(f"[backend] Launched eppo_inference for session {session_id[:8]}...")

    prior_apr = get_student_apr(user_id)
    return jsonify({
        "session_id":  session_id,
        "status":      "started",
        "scope_type":  scope_type,
        "scope_ids":   scope_ids,
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
    print("BayLearn adaptive backend — http://localhost:8000")
    print("Swagger UI             — http://localhost:8000/docs")
    app.run(host="0.0.0.0", port=8000, debug=False)