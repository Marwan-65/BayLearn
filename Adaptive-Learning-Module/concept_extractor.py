"""
concept_extractor.py
====================
Pipeline that:
  1. Reads all configuration from a .env file (no CLI arguments needed).
  2. Connects to the Input-Parsing-Module PostgreSQL database and pulls all
     chunks for a given file (FILE_ID or FILE_NAME).
  3. Assembles those chunks into a single document string.
  4. Sends the document to Groq and extracts every concept with a difficulty
     rating (1 = easiest … 5 = hardest).
  5. Inserts the extracted concepts into the Adaptive-Learning-Module
     PostgreSQL database under the specified COURSE_NAME.

Run:
    python concept_extractor.py

Required .env keys:
    CHUNK_DB_URL    — SQLAlchemy connection string for the Input-Parsing DB
    CONCEPT_DB_URL  — SQLAlchemy connection string for the Adaptive-Learning DB
    GROQ_API_KEY    — Groq API key
    COURSE_NAME     — Course name to create/reuse in the concepts DB
    EPPO_USER_ID    — Integer user ID to enroll in the course after upload
    FILE_ID         — UUID of the file in the chunk DB   (use this OR FILE_NAME)
    FILE_NAME       — file_name of the file in the chunk DB (use this OR FILE_ID)

Optional .env keys:
    GROQ_MODEL      — Groq model id  (default: llama-3.3-70b-versatile)
    MAX_CHARS       — Max document characters sent to Groq (default: 120000)
    DRY_RUN         — Set to "true" to skip writing to the concept DB

Dependencies:
    pip install psycopg2-binary sqlalchemy groq python-dotenv
"""

from __future__ import annotations

import json
import os
import sys
import textwrap
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from groq import Groq
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    ForeignKey,
    JSON,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, Session

# Load .env from the same directory as this script
load_dotenv(Path(__file__).parent / ".env")


# ---------------------------------------------------------------------------
# Config — read entirely from environment / .env
# ---------------------------------------------------------------------------

def _require(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if not val:
        print(f"ERROR: '{key}' is not set in .env", file=sys.stderr)
        sys.exit(1)
    return val


def _optional(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip() or default


CHUNK_DB_URL   = _require("CHUNK_DB_URL")
CONCEPT_DB_URL = _require("CONCEPT_DB_URL")
GROQ_API_KEY   = _require("GROQ_API_KEY")
COURSE_NAME    = _require("COURSE_NAME")
EPPO_USER_ID   = int(_require("EPPO_USER_ID"))
FILE_ID        = _optional("FILE_ID")
FILE_NAME      = _optional("FILE_NAME")
GROQ_MODEL     = _optional("GROQ_MODEL", "llama-3.3-70b-versatile")
MAX_CHARS      = int(_optional("MAX_CHARS", "120000"))
DRY_RUN        = _optional("DRY_RUN", "false").lower() == "true"

if not FILE_ID and not FILE_NAME:
    print("ERROR: Set either FILE_ID or FILE_NAME in .env", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# SQLAlchemy models — Input-Parsing-Module (read-only)
# ---------------------------------------------------------------------------

ChunkBase = declarative_base()


class UploadedFile(ChunkBase):
    __tablename__ = "uploaded_files"

    id           = Column(String, primary_key=True)
    file_name    = Column(String)
    title        = Column(String)
    source_type  = Column(String)
    total_chunks = Column(Integer)

    chunks = relationship("Chunk", back_populates="file", order_by="Chunk.chunk_index")


class Chunk(ChunkBase):
    __tablename__ = "chunks"

    id             = Column(String, primary_key=True)
    file_id        = Column(String, ForeignKey("uploaded_files.id"))
    content        = Column(Text)
    chunk_index    = Column(Integer)
    chunk_type     = Column(String)
    chunk_metadata = Column(JSON)

    file = relationship("UploadedFile", back_populates="chunks")


# ---------------------------------------------------------------------------
# SQLAlchemy models — Adaptive-Learning-Module (write)
# ---------------------------------------------------------------------------

ConceptBase = declarative_base()


class Course(ConceptBase):
    __tablename__ = "courses"

    id          = Column(Integer, primary_key=True)
    name        = Column(String, unique=True, nullable=False)
    uploader_id = Column(Integer, nullable=True)

    concepts = relationship("Concept", back_populates="course", cascade="all, delete-orphan")


class Concept(ConceptBase):
    __tablename__ = "concepts"

    id         = Column(Integer, primary_key=True)
    course_id  = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    name       = Column(String, nullable=False)
    difficulty = Column(Integer, nullable=False)

    course = relationship("Course", back_populates="concepts")


class CourseEnrollment(ConceptBase):
    __tablename__ = "course_enrollments"

    # No FK declarations here — the 'users' table isn't in this metadata object.
    # The FK constraints still exist in the real DB and are enforced server-side.
    user_id   = Column(Integer, primary_key=True)
    course_id = Column(Integer, primary_key=True)


class User(ConceptBase):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)


# ---------------------------------------------------------------------------
# Step 1: Fetch chunks from the Input-Parsing DB
# ---------------------------------------------------------------------------

def fetch_chunks() -> tuple[str, list[Chunk], str]:
    """
    Connect to the Input-Parsing-Module database and return
    (resolved_file_id, chunks, document_title).
    """
    engine = create_engine(CHUNK_DB_URL)
    with Session(engine) as session:
        if FILE_ID:
            db_file = session.get(UploadedFile, FILE_ID)
            if db_file is None:
                print(f"ERROR: No file found with FILE_ID={FILE_ID!r}", file=sys.stderr)
                sys.exit(1)
        else:
            db_file = (
                session.query(UploadedFile)
                .filter(UploadedFile.file_name == FILE_NAME)
                .order_by(UploadedFile.id)
                .first()
            )
            if db_file is None:
                print(f"ERROR: No file found with FILE_NAME={FILE_NAME!r}", file=sys.stderr)
                sys.exit(1)

        title = db_file.title or db_file.file_name
        print(f"[chunk-db] Resolved file: '{title}'  "
              f"(id={db_file.id}, type={db_file.source_type}, chunks={db_file.total_chunks})")

        chunks = (
            session.query(Chunk)
            .filter(Chunk.file_id == db_file.id)
            .order_by(Chunk.chunk_index)
            .all()
        )
        session.expunge_all()

    print(f"[chunk-db] Loaded {len(chunks)} chunks.")
    return db_file.id, chunks, title


# ---------------------------------------------------------------------------
# Step 2: Assemble document string
# ---------------------------------------------------------------------------

def assemble_document(chunks: list[Chunk], title: str = "") -> str:
    """Concatenate chunk content into a single readable document."""
    parts: list[str] = []
    if title:
        parts.append(f"# {title}\n")

    for chunk in chunks:
        ctype = (chunk.chunk_type or "text").lower()
        if ctype == "image":
            meta = chunk.chunk_metadata or {}
            path = meta.get("image_path", f"chunk_{chunk.chunk_index}")
            parts.append(f"[IMAGE: {path}]")
        else:
            content = (chunk.content or "").strip()
            if content:
                parts.append(content)

    document = "\n\n".join(parts)
    print(f"[assemble] Document: {len(document):,} characters, {len(chunks)} chunks.")
    return document


# ---------------------------------------------------------------------------
# Step 3: Extract concepts via Groq
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = textwrap.dedent("""\
    You are an expert educational content analyser.
    Your task is to read a document and extract ALL the academic/technical
    concepts that a student will need to understand and will be examined on.

    For each concept provide:
      - "name": a concise concept name (2–6 words, lower case)
      - "difficulty": an integer 1–5 where
          1 = introductory / definitional
          2 = foundational understanding required
          3 = moderate — requires some reasoning or application
          4 = advanced — requires synthesis or deeper analysis
          5 = expert — graduate-level or highly complex

    Rules:
    - Be exhaustive: extract EVERY meaningful concept, not just headings.
    - Do NOT include meta-concepts like "exam tips" or "study advice".
    - Do NOT duplicate concepts.
    - Return ONLY valid JSON — no markdown fences, no extra text.

    Output format (JSON array):
    [
      {"name": "concept name", "difficulty": 3},
      ...
    ]
""")


def extract_concepts_from_document(document: str) -> list[dict]:
    """Send the assembled document to Groq and parse the returned concept list."""
    client = Groq(api_key=GROQ_API_KEY)

    if len(document) > MAX_CHARS:
        print(f"[groq] Document exceeds {MAX_CHARS:,} chars — truncating.")
        document = document[:MAX_CHARS] + "\n\n[... document truncated ...]"

    user_message = (
        "Here is the document. Extract all concepts as instructed.\n\n"
        f"---\n{document}\n---"
    )

    print(f"[groq] Sending request to model={GROQ_MODEL} ...")
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ],
        temperature=0.2,
        max_tokens=4096,
    )

    raw_output = response.choices[0].message.content.strip()
    print(f"[groq] Response received ({len(raw_output)} chars).")

    # Strip accidental markdown fences
    if raw_output.startswith("```"):
        raw_output = raw_output.split("```")[1]
        if raw_output.startswith("json"):
            raw_output = raw_output[4:]
        raw_output = raw_output.rsplit("```", 1)[0]

    concepts = json.loads(raw_output)

    validated: list[dict] = []
    for item in concepts:
        name       = str(item.get("name", "")).strip()
        difficulty = int(item.get("difficulty", 3))
        if not name:
            continue
        difficulty = max(1, min(5, difficulty))
        validated.append({"name": name, "difficulty": difficulty})

    print(f"[groq] Extracted {len(validated)} concepts.")
    return validated


# ---------------------------------------------------------------------------
# Step 4: Upload concepts to the Adaptive-Learning DB
# ---------------------------------------------------------------------------

def upload_concepts(concepts: list[dict]) -> tuple[int, int]:
    """
    Upsert the course row, insert extracted concepts, and enroll EPPO_USER_ID
    in the course (inserts into course_enrollments if not already present).
    Concepts already present for this course (same name) are silently skipped.
    Returns (course_id, n_inserted).
    """
    engine = create_engine(CONCEPT_DB_URL)

    with Session(engine) as session:
        # ── Upsert course ──────────────────────────────────────────────────
        course = session.query(Course).filter(Course.name == COURSE_NAME).first()
        if course is None:
            course = Course(name=COURSE_NAME)
            session.add(course)
            session.flush()
            print(f"[concept-db] Created course '{COURSE_NAME}' (id={course.id}).")
        else:
            print(f"[concept-db] Reusing existing course '{COURSE_NAME}' (id={course.id}).")

        course_id = course.id

        # ── Insert concepts (skip duplicates) ──────────────────────────────
        existing_names: set[str] = {
            row.name
            for row in session.query(Concept.name)
                               .filter(Concept.course_id == course_id)
                               .all()
        }

        inserted = 0
        skipped  = 0
        for item in concepts:
            if item["name"] in existing_names:
                skipped += 1
                continue
            session.add(Concept(
                course_id  = course_id,
                name       = item["name"],
                difficulty = item["difficulty"],
            ))
            existing_names.add(item["name"])
            inserted += 1

        # ── Enroll user in the course (upsert via get-or-create) ───────────
        user = session.get(User, EPPO_USER_ID)
        if user is None:
            print(
                f"[concept-db] WARNING: user_id={EPPO_USER_ID} does not exist in users; "
                f"skipping enrollment for course_id={course_id}."
            )
        else:
            enrollment = session.get(CourseEnrollment, (EPPO_USER_ID, course_id))
            if enrollment is None:
                session.add(CourseEnrollment(user_id=EPPO_USER_ID, course_id=course_id))
                print(f"[concept-db] Enrolled user_id={EPPO_USER_ID} in course_id={course_id}.")
            else:
                print(f"[concept-db] user_id={EPPO_USER_ID} already enrolled in course_id={course_id}.")

        session.commit()

    print(f"[concept-db] Inserted {inserted} new concepts, skipped {skipped} duplicates.")
    return course_id, inserted


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"\n{'='*60}")
    print(f"  Concept Extractor")
    print(f"  Course   : {COURSE_NAME}")
    print(f"  User ID  : {EPPO_USER_ID}")
    print(f"  File     : {FILE_ID or FILE_NAME}")
    print(f"  Model    : {GROQ_MODEL}")
    print(f"  Dry run  : {DRY_RUN}")
    print(f"{'='*60}\n")

    # Step 1
    print("=== Step 1: Fetching chunks ===")
    _, chunks, title = fetch_chunks()

    # Step 2
    print("\n=== Step 2: Assembling document ===")
    document = assemble_document(chunks, title=title)

    # Step 3
    print("\n=== Step 3: Extracting concepts via Groq ===")
    concepts = extract_concepts_from_document(document)

    print("\nExtracted concepts:")
    for i, c in enumerate(concepts, 1):
        bar = "█" * c["difficulty"] + "░" * (5 - c["difficulty"])
        print(f"  {i:>3}. [{bar}] diff={c['difficulty']}  {c['name']}")

    # Step 4
    if DRY_RUN:
        print("\n[dry-run] Skipping database upload.")
    else:
        print("\n=== Step 4: Uploading concepts to concept DB ===")
        course_id, n_inserted = upload_concepts(concepts)
        print(f"\nDone. course_id={course_id}, {n_inserted} concepts uploaded.")


if __name__ == "__main__":
    main()
