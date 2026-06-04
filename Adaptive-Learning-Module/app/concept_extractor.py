"""
concept_extractor.py
====================
Library module — called programmatically by backend.py only.

Public API:
    extract_and_store(file_ids, course_id, course_name, user_id, dry_run=False)

    file_ids    : list of chunk DB file UUIDs
    course_id   : chunk DB course UUID (used as concept DB course PK)
    course_name : resolved from chunk DB — stored in concept DB courses.name
    user_id     : chunk DB user UUID (used as concept DB user PK)

Both DBs now use the same UUIDs for users and courses, so no integer mapping needed.

Required .env keys:
    CHUNK_DB_URL    — SQLAlchemy URL for the Input-Parsing DB
    CONCEPT_DB_URL  — SQLAlchemy URL for the Adaptive-Learning DB
    GROQ_API_KEY    — Groq API key

Optional .env keys:
    GROQ_MODEL          — default: llama-3.3-70b-versatile
    MAX_CHARS           — max chars per Groq call   (default: 40000)
    BATCH_SIZE          — chunks per batch call     (default: 10)
    BATCH_THRESHOLD     — char count above which batching kicks in (default: 40000)
"""

from __future__ import annotations

import json
import os
import sys
import textwrap
import uuid
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from groq import Groq
from sqlalchemy import (
    Column, String, Integer, Text, ForeignKey, JSON,
    create_engine, text,
)
from sqlalchemy.orm import declarative_base, Session

load_dotenv(Path(__file__).parent / ".env")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _require(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if not val:
        print(f"ERROR: '{key}' is not set in .env", file=sys.stderr)
        sys.exit(1)
    return val


def _optional(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip() or default


CHUNK_DB_URL    = _require("CHUNK_DB_URL")
CONCEPT_DB_URL  = _require("CONCEPT_DB_URL")
GROQ_API_KEY    = _require("GROQ_API_KEY")
GROQ_MODEL      = _optional("GROQ_MODEL",      "llama-3.3-70b-versatile")
MAX_CHARS       = int(_optional("MAX_CHARS",       "40000"))
BATCH_SIZE      = int(_optional("BATCH_SIZE",      "10"))
BATCH_THRESHOLD = int(_optional("BATCH_THRESHOLD", "40000"))

VALID_CONCEPT_TYPES = {
    "algorithm", "data_structure", "paradigm",
    "theorem_or_property", "mathematical_concept",
    "hardware_concept", "system_concept",
    "protocol_or_standard", "security_concept", "language_concept",
}


# ---------------------------------------------------------------------------
# ORM — Chunk DB (read-only)
# All IDs are UUIDs stored as strings
# ---------------------------------------------------------------------------

ChunkBase = declarative_base()


class ChunkDBCourse(ChunkBase):
    __tablename__ = "courses"
    id   = Column(String, primary_key=True)
    name = Column(String, nullable=False)


class UploadedFile(ChunkBase):
    __tablename__ = "uploaded_files"
    id           = Column(String, primary_key=True)
    user_id      = Column(String, nullable=False)
    course_id    = Column(String, nullable=True)    # nullable — uncategorized files
    file_name    = Column(String, nullable=False)
    file_type    = Column(String)
    source_type  = Column(String)
    title        = Column(String)
    file_path    = Column(String)
    total_chunks = Column(Integer)


class Chunk(ChunkBase):
    __tablename__ = "chunks"
    id             = Column(String, primary_key=True)
    section_id     = Column(String)
    file_id        = Column(String, ForeignKey("uploaded_files.id"))
    content        = Column(Text)
    chunk_index    = Column(Integer)
    chunk_type     = Column(String)
    chunk_metadata = Column(JSON)


# ---------------------------------------------------------------------------
# Step 1: Chunk DB helpers
# ---------------------------------------------------------------------------

def get_file_info(file_id: str) -> dict | None:
    """
    Return { id, course_id, course_name, title, file_name } for a file UUID.
    course_id / course_name are None if file is uncategorized.
    """
    engine = create_engine(CHUNK_DB_URL)
    with Session(engine) as session:
        row = session.execute(text("""
            SELECT uf.id, uf.course_id, co.name AS course_name,
                   uf.title, uf.file_name
            FROM   uploaded_files uf
            LEFT JOIN courses co ON co.id = uf.course_id
            WHERE  uf.id = CAST(:fid AS uuid)
        """), {"fid": file_id}).fetchone()
    if row is None:
        return None
    return {
        "id":          row[0],
        "course_id":   row[1],
        "course_name": row[2],
        "title":       row[3] or row[4],
    }


def get_course_info(course_id: str) -> dict | None:
    """Return { id, name } for a chunk DB course UUID."""
    engine = create_engine(CHUNK_DB_URL)
    with Session(engine) as session:
        row = session.execute(text("""
            SELECT id::text, name FROM courses WHERE id = CAST(:cid AS uuid)
        """), {"cid": course_id}).fetchone()
    if row is None:
        return None
    return {"id": row[0], "name": row[1]}


def fetch_chunks_for_files(file_ids: list[str]) -> list[tuple[str, list, str]]:
    """
    Fetch chunks for one or more file UUIDs from the chunk DB.
    Returns list of (file_id, chunks, title).
    Skips files not found with a warning.
    """
    engine = create_engine(CHUNK_DB_URL)
    results = []
    with Session(engine) as session:
        for fid in file_ids:
            row = session.execute(text("""
                SELECT id::text, title, file_name FROM uploaded_files WHERE id = CAST(:fid AS uuid)
            """), {"fid": fid}).fetchone()
            if row is None:
                print(f"[chunk-db] WARNING: file '{fid}' not found, skipping.",
                      file=sys.stderr)
                continue
            file_uuid = row[0]
            title     = row[1] or row[2]
            chunks = session.execute(text("""
                SELECT id, file_id, content, chunk_index, chunk_type, chunk_metadata
                FROM   chunks
                WHERE  file_id = CAST(:fid AS uuid)
                ORDER  BY chunk_index
            """), {"fid": file_uuid}).fetchall()
            # wrap rows as simple objects so _build_batch_text works
            chunk_objs = [_ChunkRow(c) for c in chunks]
            session.expunge_all()
            print(f"[chunk-db] '{title}': {len(chunk_objs)} chunks "
                  f"(id={file_uuid})")
            results.append((file_uuid, chunk_objs, title))
    return results


class _ChunkRow:
    """Thin wrapper so raw SQL rows behave like ORM objects."""
    __slots__ = ("id", "file_id", "content", "chunk_index",
                 "chunk_type", "chunk_metadata")

    def __init__(self, row):
        self.id             = row[0]
        self.file_id        = row[1]
        self.content        = row[2]
        self.chunk_index    = row[3]
        self.chunk_type     = row[4]
        self.chunk_metadata = row[5]


# ---------------------------------------------------------------------------
# Step 2: Extract concepts via Groq (adaptive batching)
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = textwrap.dedent("""\
    You are an expert engineering educator with deep knowledge of Computer
    Engineering, Computer Science, Electrical Engineering, Communications,
    Embedded Systems, Cybersecurity, Cloud Computing, and Applied Mathematics.

    Extract all academic concepts from a university-level engineering course
    document that a student must master and may be assessed on.

    ── WHAT A CONCEPT IS ────────────────────────────────────────────────
    A concept is a distinct, named idea that:
      • appears as a section or topic in a standard textbook on the subject
      • has its own prerequisites and unlocks further topics
      • requires dedicated study time — not just a definition lookup

    Ask yourself: "Would a course dedicate at least one lecture to this alone?"
    If NO → it is not a concept worth extracting.

    ── NAMING RULES ─────────────────────────────────────────────────────
    • Use standard textbook / IEEE / ACM terminology. Singular, lowercase.
    • Full name as canonical — put acronyms in aliases.
    • Be specific — one concept per independently teachable unit.
    • Merge synonyms into aliases.

    ── GRANULARITY RULE ─────────────────────────────────────────────────
    Too broad  : "sorting algorithms", "graph algorithms", "network security"
    Too narrow : "incrementing a loop counter", "ring 0 privilege bit"
    Just right : "cpu scheduling", "virtual memory", "public-key cryptography"

    ── WHAT NOT TO EXTRACT ──────────────────────────────────────────────
    1. Product / tool names (extract the concept they implement instead)
    2. Performance metrics and formulas (turnaround time, burst time)
    3. Micro implementation details (ring 0, trap instruction, inode number)
    4. Near-duplicate variants (extract one parent concept)
    5. Contextual / relative terms used as standalone entries

    ── DIFFICULTY SCALE ─────────────────────────────────────────────────
    1 Definitional  2 Foundational  3 Applied  4 Advanced  5 Expert

    ── CONCEPT TYPES ────────────────────────────────────────────────────
    algorithm | data_structure | paradigm | theorem_or_property |
    mathematical_concept | hardware_concept | system_concept |
    protocol_or_standard | security_concept | language_concept

    ── OUTPUT ───────────────────────────────────────────────────────────
    Return ONLY a valid JSON array. No markdown, no preamble.
    Each item: { "name": str, "aliases": [str], "difficulty": int, "type": str }
""")


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def _build_batch_text(chunks: list, title: str = "") -> str:
    parts: list[str] = []
    if title:
        parts.append(f"# {title}\n")
    for chunk in chunks:
        ctype = (chunk.chunk_type or "text").lower()
        if ctype == "image":
            meta = chunk.chunk_metadata or {}
            parts.append(f"[IMAGE: {meta.get('image_path', str(chunk.chunk_index))}]")
        else:
            content = (chunk.content or "").strip()
            if content:
                parts.append(content)
    return "\n\n".join(parts)


def _call_groq(client: Groq, batch_text: str, batch_label: str) -> list[dict]:
    if len(batch_text) > MAX_CHARS:
        batch_text = batch_text[:MAX_CHARS] + "\n\n[... truncated ...]"
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user",   "content": (
                "Extract all concepts as instructed.\n\n"
                f"---\n{batch_text}\n---"
            )},
        ],
        temperature=0.2,
        max_tokens=4096,
    )
    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0]
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"  [groq] WARNING: JSON parse error on {batch_label}: {exc}",
              file=sys.stderr)
        return []
    validated = []
    for item in parsed:
        name = str(item.get("name", "")).strip().lower()
        if not name:
            continue
        difficulty   = max(1, min(5, int(item.get("difficulty", 3))))
        raw_type     = str(item.get("type", "unknown")).strip().lower()
        concept_type = raw_type if raw_type in VALID_CONCEPT_TYPES else "unknown"
        raw_aliases  = item.get("aliases", [])
        aliases = [
            str(a).strip().lower() for a in
            (raw_aliases if isinstance(raw_aliases, list) else [])
            if str(a).strip() and str(a).strip().lower() != name
        ]
        validated.append({"name": name, "aliases": aliases,
                           "difficulty": difficulty, "type": concept_type})
    return validated


def _merge_batches(batch_results: list[list[dict]]) -> list[dict]:
    canonical_map: dict[str, dict] = {}
    alias_index:   dict[str, str]  = {}
    for batch in batch_results:
        for concept in batch:
            norm_name    = _norm(concept["name"])
            norm_aliases = [_norm(a) for a in concept["aliases"]]
            existing_key: Optional[str] = None
            if norm_name in canonical_map:
                existing_key = norm_name
            elif norm_name in alias_index:
                existing_key = alias_index[norm_name]
            else:
                for na in norm_aliases:
                    if na in canonical_map:
                        existing_key = na; break
                    if na in alias_index:
                        existing_key = alias_index[na]; break
            if existing_key is not None:
                entry = canonical_map[existing_key]
                existing_norms = {_norm(a) for a in entry["aliases"]}
                for na, raw_a in zip(norm_aliases, concept["aliases"]):
                    if na not in existing_norms and na != existing_key:
                        entry["aliases"].append(raw_a)
                        existing_norms.add(na)
                        alias_index.setdefault(na, existing_key)
                entry["difficulty"] = max(entry["difficulty"], concept["difficulty"])
                if entry["type"] == "unknown" and concept["type"] != "unknown":
                    entry["type"] = concept["type"]
            else:
                entry = {
                    "name":       concept["name"],
                    "aliases":    list(dict.fromkeys(concept["aliases"])),
                    "difficulty": concept["difficulty"],
                    "type":       concept["type"],
                }
                canonical_map[norm_name] = entry
                alias_index[norm_name]   = norm_name
                for na, raw_a in zip(norm_aliases, concept["aliases"]):
                    alias_index.setdefault(na, norm_name)
    return list(canonical_map.values())


def extract_concepts_from_chunks(chunks: list, title: str = "") -> list[dict]:
    client      = Groq(api_key=GROQ_API_KEY)
    text_chunks = [c for c in chunks
                   if (c.chunk_type or "text").lower() != "image"]
    total_chars  = sum(len(c.content or "") for c in text_chunks)
    use_batching = total_chars >= BATCH_THRESHOLD
    print(f"[groq] {'Long' if use_batching else 'Short'} document "
          f"({total_chars:,} chars) → "
          f"{'batched' if use_batching else 'single-call'} "
          f"(model={GROQ_MODEL})")
    batch_results: list[list[dict]] = []
    if not use_batching:
        full_text = _build_batch_text(text_chunks, title=title)
        print(f"  [groq] Sending ({len(full_text):,} chars) ...")
        concepts = _call_groq(client, full_text, "single-call")
        print(f"  [groq] → {len(concepts)} concepts extracted.")
        batch_results.append(concepts)
    else:
        total_batches = (len(text_chunks) + BATCH_SIZE - 1) // BATCH_SIZE
        for i in range(total_batches):
            batch_chunks = text_chunks[i * BATCH_SIZE: (i + 1) * BATCH_SIZE]
            label        = f"batch {i+1}/{total_batches}"
            batch_text   = _build_batch_text(
                batch_chunks, title=title if i == 0 else "")
            print(f"  [groq] Sending {label} ({len(batch_text):,} chars) ...")
            concepts = _call_groq(client, batch_text, label)
            print(f"  [groq] {label} → {len(concepts)} concepts.")
            batch_results.append(concepts)
    merged    = _merge_batches(batch_results)
    raw_total = sum(len(b) for b in batch_results)
    print(f"[groq] Merged: {len(merged)} unique "
          f"({raw_total} total, {raw_total - len(merged)} duplicates removed).")
    return merged


# ---------------------------------------------------------------------------
# Step 3: Save to Concept DB (UUID-based)
# ---------------------------------------------------------------------------

def save_concepts(
    concepts:    list[dict],
    course_id:   str,          # chunk DB course UUID → used as concept DB course PK
    course_name: str,          # for display / UNIQUE constraint
    user_id:     str,          # chunk DB user UUID → used as concept DB user PK
    file_ids:    list[str],    # chunk DB file UUIDs → stored in concept_files
) -> tuple[str, int]:
    """
    Upsert course, insert new concepts, link to files, enroll user.
    Returns (course_id, n_inserted).

    Both course_id and user_id are the chunk DB UUIDs reused as PKs
    in the concept DB — no integer mapping needed.
    """
    engine = create_engine(CONCEPT_DB_URL)
    with Session(engine) as session:

        resolved_course_id = course_id

        # Reuse an existing course row by UUID or name before inserting.
        existing_course = session.execute(text("""
            SELECT id FROM courses WHERE id = :cid
        """), {"cid": course_id}).fetchone()

        if existing_course is not None:
            print(f"[concept-db] Reusing course '{course_name}' (id={course_id}).")
        else:
            existing_course_by_name = session.execute(text("""
                SELECT id FROM courses WHERE name = :name
            """), {"name": course_name}).fetchone()

            if existing_course_by_name is not None:
                resolved_course_id = existing_course_by_name[0]
                print(f"[concept-db] Reusing existing course '{course_name}' "
                      f"(id={resolved_course_id}) for incoming id={course_id}.")
            else:
                session.execute(text("""
                    INSERT INTO courses (id, name, created_at)
                    VALUES (:cid, :name, NOW())
                """), {"cid": course_id, "name": course_name})
                session.flush()   # ensure the insert is sent to the DB
                # Commit here to avoid FK visibility issues across adapters/clients.
                # This makes the course row durable before inserting concepts.
                session.commit()
                # Re-open a transaction for the remainder of the work
                session.begin()
                print(f"[concept-db] Created course '{course_name}' (id={course_id}).")

        course_id = resolved_course_id

        # Existing concept names for this course
        existing_names = {
            _norm(row[0]) for row in session.execute(text("""
                SELECT name FROM concepts WHERE course_id = :cid
            """), {"cid": course_id}).fetchall()
        }

        # Insert new concepts with generated UUIDs
        inserted = 0
        new_concept_ids: list[str] = []
        for item in concepts:
            if _norm(item["name"]) in existing_names:
                continue
            concept_uuid = str(uuid.uuid4())
            session.execute(text("""
                INSERT INTO concepts (id, course_id, name, difficulty,
                                      aliases, concept_type)
                VALUES (:id, :cid, :name, :diff, CAST(:aliases AS jsonb), :ctype)
            """), {
                "id":      concept_uuid,
                "cid":     course_id,
                "name":    item["name"],
                "diff":    item["difficulty"],
                "aliases": json.dumps(item["aliases"]),
                "ctype":   item["type"],
            })
            existing_names.add(_norm(item["name"]))
            new_concept_ids.append(concept_uuid)
            inserted += 1

        # Link ALL concepts in this course to the uploaded files
        # (not just new ones — so re-running on new files links existing concepts too)
        all_concept_ids = [
            row[0] for row in session.execute(text("""
                SELECT id FROM concepts WHERE course_id = :cid
            """), {"cid": course_id}).fetchall()
        ]
        for cid in all_concept_ids:
            for fid in file_ids:
                session.execute(text("""
                    INSERT INTO concept_files (concept_id, file_id)
                    VALUES (:cid, :fid)
                    ON CONFLICT (concept_id, file_id) DO NOTHING
                """), {"cid": cid, "fid": fid})

        # Upsert user in concept DB using chunk DB user UUID as PK
        session.execute(text("""
            INSERT INTO users (id, email, username, created_at)
            VALUES (:uid, :email, :username, NOW())
            ON CONFLICT (id) DO NOTHING
        """), {
            "uid":      user_id,
            "email":    f"user_{user_id}@placeholder.com",
            "username": f"user_{user_id[:8]}",
        })

        # Enroll user in course
        session.execute(text("""
            INSERT INTO course_enrollments (user_id, course_id)
            VALUES (:uid, :cid)
            ON CONFLICT (user_id, course_id) DO NOTHING
        """), {"uid": user_id, "cid": course_id})
        print(f"[concept-db] Enrolled user {user_id[:8]}... "
              f"in course {course_id[:8]}...")

        session.commit()

    skipped = len(concepts) - inserted
    print(f"[concept-db] {inserted} new concepts inserted, "
          f"{skipped} skipped (duplicates).")
    return course_id, inserted


# ---------------------------------------------------------------------------
# Public API — called by backend.py
# ---------------------------------------------------------------------------

def already_extracted(file_id: str) -> bool:
    """
    Check if concepts have already been extracted for this file UUID.
    Used by extract_and_store to skip files that were already processed.
    """
    engine = create_engine(CONCEPT_DB_URL)
    with Session(engine) as session:
        try:
            count = session.execute(text("""
                SELECT COUNT(*) FROM concept_files WHERE file_id = :fid
            """), {"fid": file_id}).scalar()
            return (count or 0) > 0
        except Exception:
            return False


def already_extracted_for_course(course_id: str) -> bool:
    """
    Check if concepts have already been extracted for this course UUID.
    Used by backend.py for course-scope session checks.
    """
    engine = create_engine(CONCEPT_DB_URL)
    with Session(engine) as session:
        try:
            count = session.execute(text("""
                SELECT COUNT(*) FROM concepts WHERE course_id = :cid
            """), {"cid": course_id}).scalar()
            return (count or 0) > 0
        except Exception:
            return False


def _ensure_enrollment(course_id: str, user_id: str) -> None:
    """
    Upsert user and enroll in course without re-extracting anything.
    Called when all files are already extracted but enrollment may be missing.
    """
    engine = create_engine(CONCEPT_DB_URL)
    with Session(engine) as session:
        session.execute(text("""
            INSERT INTO users (id, email, username, created_at)
            VALUES (:uid, :email, :username, NOW())
            ON CONFLICT (id) DO NOTHING
        """), {"uid": user_id,
               "email":    f"user_{user_id}@placeholder.com",
               "username": f"user_{user_id[:8]}"})
        session.execute(text("""
            INSERT INTO course_enrollments (user_id, course_id)
            VALUES (:uid, :cid)
            ON CONFLICT (user_id, course_id) DO NOTHING
        """), {"uid": user_id, "cid": course_id})
        session.commit()
    print(f"[concept-db] Enrollment ensured for user {user_id[:8]}... "
          f"in course {course_id[:8]}...")


def extract_and_store(
    file_ids:    list[str],         # chunk DB file UUIDs
    course_id:   str | None,        # chunk DB course UUID (None → uncategorized)
    course_name: str,               # resolved by backend from chunk DB
    user_id:     str,               # chunk DB user UUID
    dry_run:     bool = False,
    force:       bool = False,      # re-extract even if already done
) -> dict:
    """
    Full pipeline — works for both course mode and files mode:

      1. Filter out files that already have concepts extracted
         (checked per file via concept_files) — unless force=True
      2. Fetch chunks from chunk DB for the remaining files only
      3. Extract concepts via Groq (adaptive batching)
      4. Save to concept DB — concepts linked to course AND files

    For course mode:
        backend passes all file IDs belonging to the course.
        Already-processed files are skipped — only new uploads are extracted.

    For files mode:
        backend passes the selected file UUIDs.
        Already-processed files are skipped — no duplicate Groq calls.

    If ALL files are already extracted:
        skips Groq entirely, just ensures enrollment is up to date.

    Returns {"course_id": str, "n_inserted": int, "n_concepts": int,
             "skipped_files": int}
    """
    # Stable UUID for uncategorized files
    if not course_id:
        course_id   = str(uuid.uuid5(uuid.NAMESPACE_DNS,
                                     "uncategorized:" + ",".join(sorted(file_ids))))
        course_name = course_name or "uncategorized"

    # Filter out already-extracted files
    if force:
        files_to_extract = list(file_ids)
        skipped_files    = 0
    else:
        files_to_extract = [fid for fid in file_ids
                            if not already_extracted(fid)]
        skipped_files    = len(file_ids) - len(files_to_extract)
        if skipped_files:
            print(f"[extractor] {skipped_files}/{len(file_ids)} file(s) already "
                  f"extracted — skipping. "
                  f"{len(files_to_extract)} new file(s) to process.")

    # All files already extracted — just ensure enrollment
    if not files_to_extract:
        print("[extractor] All files already extracted. "
              "Ensuring user enrollment...")
        _ensure_enrollment(course_id, user_id)
        return {"course_id":     course_id,
                "n_inserted":    0,
                "n_concepts":    0,
                "skipped_files": skipped_files}

    print(f"\n{'='*60}")
    print(f"  Concept Extractor")
    print(f"  Course  : {course_name} ({course_id[:8]}...)")
    print(f"  User    : {user_id[:8]}...")
    print(f"  Files   : {files_to_extract}")
    print(f"  Skipped : {skipped_files} already extracted")
    print(f"  Model   : {GROQ_MODEL}")
    print(f"{'='*60}\n")

    file_results = fetch_chunks_for_files(files_to_extract)
    if not file_results:
        print("ERROR: No files found.", file=sys.stderr)
        return {"course_id": None, "n_inserted": 0,
                "n_concepts": 0, "skipped_files": skipped_files}

    resolved_ids: list[str] = []
    all_chunks:   list      = []
    combined_title = ""
    for fid, chunks, title in file_results:
        resolved_ids.append(fid)
        all_chunks.extend(chunks)
        combined_title = combined_title or title

    print("\n=== Extracting concepts ===")
    concepts = extract_concepts_from_chunks(all_chunks, title=combined_title)

    if dry_run:
        print("[dry-run] Skipping DB write.")
        return {"course_id": None, "n_inserted": 0,
                "n_concepts": len(concepts), "skipped_files": skipped_files}

    print("\n=== Saving to concept DB ===")
    course_id, n_inserted = save_concepts(
        concepts, course_id, course_name, user_id, resolved_ids
    )
    return {"course_id":     course_id,
            "n_inserted":    n_inserted,
            "n_concepts":    len(concepts),
            "skipped_files": skipped_files}