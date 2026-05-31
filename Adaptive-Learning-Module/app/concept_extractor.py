"""
concept_extractor.py
====================
Can be run two ways:

  1. Standalone (.env-based, original behaviour):
       python concept_extractor.py

  2. Called programmatically by the backend:
       from concept_extractor import extract_and_store
       extract_and_store(
           file_ids=["uuid-1", "uuid-2"],
           course_name="Algorithms",
           user_id=3,
       )

Extraction strategy (adaptive):
  - Short documents (< BATCH_THRESHOLD chars) -> single Groq call.
  - Long  documents (>= BATCH_THRESHOLD chars) -> chunk-batched calls,
    results merged and deduplicated.

Supported domains:
  Primary  : Computer Science, Computer Engineering, Software Engineering
  Secondary: Electrical Engineering, Communications, Embedded Systems,
             Cybersecurity, Cloud Computing, Machine Learning / AI,
             Physics (CE curricula), Mathematics

Required .env keys:
    CHUNK_DB_URL    — SQLAlchemy URL for the Input-Parsing DB
    CONCEPT_DB_URL  — SQLAlchemy URL for the Adaptive-Learning DB
    GROQ_API_KEY    — Groq API key

Optional .env keys (standalone mode only):
    COURSE_NAME         — course to create/reuse
    EPPO_USER_ID        — user to enroll
    FILE_ID             — UUID of file in chunk DB  (use this OR FILE_NAME)
    FILE_NAME           — file_name in chunk DB     (use this OR FILE_ID)
    GROQ_MODEL          — default: llama-3.3-70b-versatile
    MAX_CHARS           — max chars per Groq call   (default: 40000)
    BATCH_SIZE          — chunks per batch call     (default: 10)
    BATCH_THRESHOLD     — char count above which batching kicks in (default: 40000)
    DRY_RUN             — "true" to skip DB writes

Schema migration (run once):
    ALTER TABLE concepts
        ADD COLUMN IF NOT EXISTS aliases      JSONB NOT NULL DEFAULT '[]';
    ALTER TABLE concepts
        ADD COLUMN IF NOT EXISTS concept_type TEXT  NOT NULL DEFAULT 'unknown';

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
    Column, Integer, String, Text, ForeignKey, JSON,
    create_engine, text,
)
from sqlalchemy.orm import declarative_base, relationship, Session

load_dotenv(Path(__file__).parent / ".env")


# ---------------------------------------------------------------------------
# Config helpers
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
DRY_RUN         = _optional("DRY_RUN", "false").lower() == "true"

VALID_CONCEPT_TYPES = {
    "algorithm",
    "data_structure",
    "paradigm",
    "theorem_or_property",
    "mathematical_concept",
    "hardware_concept",
    "system_concept",
    "protocol_or_standard",
    "security_concept",
    "language_concept",
}


# ---------------------------------------------------------------------------
# ORM — Input-Parsing DB (read-only)
# ---------------------------------------------------------------------------

ChunkBase = declarative_base()


class UploadedFile(ChunkBase):
    __tablename__ = "uploaded_files"
    id           = Column(String, primary_key=True)
    file_name    = Column(String)
    title        = Column(String)
    source_type  = Column(String)
    total_chunks = Column(Integer)
    chunks       = relationship("Chunk", back_populates="file",
                                order_by="Chunk.chunk_index")


class Chunk(ChunkBase):
    __tablename__ = "chunks"
    id             = Column(String, primary_key=True)
    file_id        = Column(String, ForeignKey("uploaded_files.id"))
    content        = Column(Text)
    chunk_index    = Column(Integer)
    chunk_type     = Column(String)
    chunk_metadata = Column(JSON)
    file           = relationship("UploadedFile", back_populates="chunks")


# ---------------------------------------------------------------------------
# ORM — Adaptive-Learning DB (read + write)
# ---------------------------------------------------------------------------

ConceptBase = declarative_base()


class Course(ConceptBase):
    __tablename__ = "courses"
    id          = Column(Integer, primary_key=True)
    name        = Column(String, unique=True, nullable=False)
    uploader_id = Column(Integer, nullable=True)
    concepts    = relationship("Concept", back_populates="course",
                               cascade="all, delete-orphan")


class Concept(ConceptBase):
    __tablename__ = "concepts"
    id           = Column(Integer, primary_key=True)
    course_id    = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"),
                          nullable=False)
    name         = Column(String, nullable=False)
    difficulty   = Column(Integer, nullable=False)
    aliases      = Column(JSON, nullable=False, default=list)
    concept_type = Column(String, nullable=False, default="unknown")
    course       = relationship("Course", back_populates="concepts")


class CourseEnrollment(ConceptBase):
    __tablename__ = "course_enrollments"
    user_id   = Column(Integer, primary_key=True)
    course_id = Column(Integer, primary_key=True)


class User(ConceptBase):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)


# ---------------------------------------------------------------------------
# Step 1: Fetch chunks — single file (standalone) or multiple files (backend)
# ---------------------------------------------------------------------------

def fetch_chunks_single(file_id: str = "", file_name: str = "") -> tuple[str, list, str]:
    """
    Fetch chunks for one file identified by file_id or file_name.
    Used by standalone main().
    """
    engine = create_engine(CHUNK_DB_URL)
    with Session(engine) as session:
        if file_id:
            db_file = session.get(UploadedFile, file_id)
            if db_file is None:
                print(f"ERROR: No file found with FILE_ID={file_id!r}", file=sys.stderr)
                sys.exit(1)
        else:
            db_file = (
                session.query(UploadedFile)
                .filter(UploadedFile.file_name == file_name)
                .order_by(UploadedFile.id)
                .first()
            )
            if db_file is None:
                print(f"ERROR: No file found with FILE_NAME={file_name!r}", file=sys.stderr)
                sys.exit(1)

        title  = db_file.title or db_file.file_name
        chunks = (
            session.query(Chunk)
            .filter(Chunk.file_id == db_file.id)
            .order_by(Chunk.chunk_index)
            .all()
        )
        session.expunge_all()

    print(f"[chunk-db] '{title}': {len(chunks)} chunks (id={db_file.id})")
    return str(db_file.id), chunks, title


def fetch_chunks_for_files(file_ids: list[str]) -> list[tuple[str, list, str]]:
    """
    Fetch chunks for one or more files.
    Returns list of (resolved_file_id, chunks, title).
    Skips files not found with a warning.
    Used by extract_and_store() called from the backend.
    """
    engine = create_engine(CHUNK_DB_URL)
    results = []
    with Session(engine) as session:
        for fid in file_ids:
            db_file = session.get(UploadedFile, fid)
            if db_file is None:
                db_file = (
                    session.query(UploadedFile)
                    .filter(UploadedFile.file_name == fid)
                    .first()
                )
            if db_file is None:
                print(f"[chunk-db] WARNING: file '{fid}' not found, skipping.",
                      file=sys.stderr)
                continue
            title  = db_file.title or db_file.file_name
            chunks = (
                session.query(Chunk)
                .filter(Chunk.file_id == db_file.id)
                .order_by(Chunk.chunk_index)
                .all()
            )
            session.expunge_all()
            print(f"[chunk-db] '{title}': {len(chunks)} chunks (id={db_file.id})")
            results.append((str(db_file.id), chunks, title))
    return results


# ---------------------------------------------------------------------------
# Step 2: Extract concepts — adaptive single-call or batched
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = textwrap.dedent("""\
    You are an expert engineering educator with deep knowledge of Computer
    Engineering, Computer Science, Electrical Engineering, Communications,
    Embedded Systems, Cybersecurity, Cloud Computing, and Applied Mathematics.

    Extract the core academic concepts from a university-level engineering course
    document that a student must genuinely master and may be assessed on.

    ── WHAT A CONCEPT IS ────────────────────────────────────────────────
    A concept is a distinct, named idea that:
      • appears as a section or topic in a standard textbook on the subject
      • has its own prerequisites and unlocks further topics
      • requires dedicated study time — not just a definition lookup

    Ask yourself: "Would a course dedicate at least one lecture to this alone?"
    If NO → it is not a concept worth extracting.

    ── NAMING RULES (these feed a concept dependency graph) ──────────────
    • Use standard textbook / IEEE / ACM terminology.
      CORRECT: "depth-first search"              WRONG: "the DFS thing"
      CORRECT: "pulse-width modulation"          WRONG: "PWM technique"
    • Singular form, all lowercase.
      CORRECT: "binary search tree"              WRONG: "Binary Search Trees"
    • Full name as canonical, acronym goes in aliases.
      CORRECT: "dynamic programming"             WRONG: "DP"
      CORRECT: "phase-locked loop"               WRONG: "PLL"
    • If two phrasings mean the same concept, emit only the canonical one
      and put alternatives in aliases.

    ── GRANULARITY RULE ──────────────────────────────────────────────────
    Extract at the level of a textbook chapter section — one concept per
    independently teachable idea.

    Too broad  : "sorting algorithms", "graph algorithms", "network security"
    Too narrow : "incrementing a loop counter", "ring 0 privilege bit"
    Just right : "cpu scheduling", "virtual memory", "public-key cryptography",
                 "cache coherence protocol", "breadth-first search"

    When a document covers multiple algorithms or variants of the same idea
    (e.g. FCFS, SJF, Round Robin, SRTN), extract the PARENT concept that unifies
    them ("cpu scheduling algorithms") UNLESS individual variants have meaningfully
    different prerequisite structures that a student must master separately.

    ── WHAT NOT TO EXTRACT (strict) ─────────────────────────────────────
    The following categories produce noise that degrades the dependency graph.
    NEVER extract them:

    1. PRODUCT / TOOL NAMES
       These are implementations, not concepts. Extract the concept they implement.
       ✗ "kvm", "xen", "qemu", "virtualbox", "docker", "kubernetes"
       ✗ "linux", "windows nt kernel", "openssl", "wireshark"
       ✓ "type-1 hypervisor", "container runtime", "operating system kernel"

    2. PERFORMANCE METRICS AND FORMULAS
       These are ways to measure concepts, not concepts themselves.
       ✗ "turnaround time", "burst time", "waiting time", "response time"
       ✗ "throughput", "utilisation percentage", "speedup ratio"
       ✓ "cpu scheduling" (the concept whose metrics those are)

    3. MICRO IMPLEMENTATION DETAILS
       Low-level specifics that only make sense inside a parent concept.
       ✗ "ring 0", "ring 3", "trap instruction", "hypercall instruction"
       ✗ "pcb fields", "inode number", "segment descriptor bits"
       ✓ "protection rings", "system call mechanism", "process control block"

    4. NEAR-DUPLICATE VARIANTS
       When N items differ only in a parameter, extract one parent concept.
       ✗ "type-1 full virtualization" AND "type-1 paravirtualization"
          AND "type-2 virtualization" AND "bare-metal hypervisor"
          AND "hosted hypervisor"
       ✓ "virtualization" (covers all; variants become aliases or sub-points)
       Exception: keep separate entries only when prerequisites genuinely differ.

    5. CONTEXTUAL / RELATIVE TERMS
       ✗ "noisy neighbor problem", "bottleneck resource", "limiting resource"
       ✗ "overhead", "penalty", "latency" used as standalone entries
       ✓ Only extract if the term has a precise, standalone definition in the field.

    ── DIFFICULTY SCALE ─────────────────────────────────────────────────
    1 — Definitional : what is an algorithm, logic gates, Ohm's law
    2 — Foundational : recursion, big-O notation, RC circuit analysis
    3 — Applied      : dynamic programming, graph traversal, Fourier transform
    4 — Advanced     : amortized analysis, NP-completeness, cache coherence
    5 — Expert       : computational complexity theory, distributed consensus

    ── CONCEPT TYPES ────────────────────────────────────────────────────
    Assign the single most specific type that fits.

    "algorithm"             — procedures with defined steps: merge sort,
                              backpropagation, Viterbi algorithm, RSA key generation
    "data_structure"        — organisational abstractions: red-black tree,
                              bloom filter, register file, page table
    "paradigm"              — design/programming approaches: OOP, divide and
                              conquer, event-driven architecture, TDD
    "theorem_or_property"   — proven results / laws: master theorem,
                              Nyquist-Shannon, Kirchhoff's voltage law, CAP theorem
    "mathematical_concept"  — pure/applied math: eigenvalue decomposition,
                              convolution, Bayes' theorem, z-transform
    "hardware_concept"      — circuits, microarchitecture, embedded: pipeline hazard,
                              cache replacement policy, ISR, ADC, memory-mapped I/O
    "system_concept"        — OS, cloud, distributed: virtual memory, deadlock,
                              containerisation, consensus algorithm, hypervisor
    "protocol_or_standard"  — networking/communication: TCP handshake,
                              OFDM, I2C protocol, TLS certificate chain, MQTT
    "security_concept"      — cryptography, attacks, defences: public-key
                              cryptography, SQL injection, buffer overflow, ACL
    "language_concept"      — PL theory, compiler, SE practices: static type
                              checking, garbage collection, AST, design pattern

    ── OUTPUT FIELDS ────────────────────────────────────────────────────
    "name"       : canonical concept name (follow NAMING RULES exactly)
    "aliases"    : list of 0-3 well-known alternative names or acronyms
    "difficulty" : integer 1-5 (use DIFFICULTY SCALE above)
    "type"       : exactly one value from CONCEPT TYPES above

    ── EXTRACTION RULES ─────────────────────────────────────────────────
    • Extract every concept a student must genuinely master — be thorough
      but disciplined. Quality over quantity.
    • Do NOT extract meta-concepts (exam tips, study advice, logistics).
    • Do NOT extract proper nouns that are not concepts (people, institutions).
    • Do NOT duplicate — one canonical entry per concept; merge synonyms into aliases.
    • When domain is ambiguous, prefer the engineering interpretation.
    • Return ONLY a valid JSON array. No markdown fences, no preamble.

    ── EXAMPLE — CORRECT extraction from an OS scheduling lecture ────────
    WRONG (too granular, products, metrics):
    [ "first come first served", "shortest job first", "round robin",
      "shortest remaining time next", "high priority first",
      "burst time", "turnaround time", "waiting time", "response time",
      "kvm", "xen", "ring 0", "hypercall instruction" ]

    CORRECT (teachable concepts, right granularity):
    [
      {
        "name": "cpu scheduling algorithms",
        "aliases": ["process scheduling", "cpu scheduling"],
        "difficulty": 3,
        "type": "algorithm"
      },
      {
        "name": "preemptive scheduling",
        "aliases": ["preemption"],
        "difficulty": 3,
        "type": "system_concept"
      },
      {
        "name": "multilevel feedback queue",
        "aliases": ["MLFQ"],
        "difficulty": 4,
        "type": "algorithm"
      },
      {
        "name": "priority inversion",
        "aliases": [],
        "difficulty": 4,
        "type": "system_concept"
      },
      {
        "name": "hypervisor",
        "aliases": ["virtual machine monitor", "VMM"],
        "difficulty": 3,
        "type": "system_concept"
      }
    ]
""")


def _norm(s: str) -> str:
    """Normalise a concept name for deduplication keying."""
    return " ".join(s.lower().split())


def _build_batch_text(chunks: list, title: str = "") -> str:
    """Render a list of chunks into a single text block for one Groq call."""
    parts: list[str] = []
    if title:
        parts.append(f"# {title}\n")
    for chunk in chunks:
        ctype = (chunk.chunk_type or "text").lower()
        if ctype == "image":
            meta  = chunk.chunk_metadata or {}
            path  = meta.get("image_path", f"chunk_{chunk.chunk_index}")
            parts.append(f"[IMAGE: {path}]")
        else:
            content = (chunk.content or "").strip()
            if content:
                parts.append(content)
    return "\n\n".join(parts)


def _call_groq(client: Groq, batch_text: str, batch_label: str) -> list[dict]:
    """Send one batch to Groq and return a validated list of concept dicts."""
    if len(batch_text) > MAX_CHARS:
        batch_text = batch_text[:MAX_CHARS] + "\n\n[... batch truncated ...]"

    user_message = (
        "Here is the document excerpt. Extract all concepts as instructed.\n\n"
        f"---\n{batch_text}\n---"
    )
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
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
        print(f"  [groq] WARNING: JSON parse error on {batch_label}: {exc}. "
              "Skipping batch.")
        return []

    validated: list[dict] = []
    for item in parsed:
        name = str(item.get("name", "")).strip().lower()
        if not name:
            continue
        difficulty   = max(1, min(5, int(item.get("difficulty", 3))))
        raw_type     = str(item.get("type", "unknown")).strip().lower()
        concept_type = raw_type if raw_type in VALID_CONCEPT_TYPES else "unknown"
        raw_aliases  = item.get("aliases", [])
        aliases      = [
            str(a).strip().lower()
            for a in (raw_aliases if isinstance(raw_aliases, list) else [])
            if str(a).strip()
        ]
        aliases = [a for a in aliases if a != name]
        validated.append({
            "name":       name,
            "aliases":    aliases,
            "difficulty": difficulty,
            "type":       concept_type,
        })
    return validated


def _merge_batches(batch_results: list[list[dict]]) -> list[dict]:
    """
    Merge per-batch concept lists into a single deduplicated list.
    Deduplication key: normalised canonical name OR any matching alias.
    On conflict:
      - aliases   : union
      - difficulty: maximum
      - type      : first non-'unknown' wins
    """
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
    """
    Adaptive extraction:
      - total chars < BATCH_THRESHOLD -> single Groq call
      - total chars >= BATCH_THRESHOLD -> batched calls (BATCH_SIZE chunks each)
    Results are merged and deduplicated by _merge_batches.
    """
    client      = Groq(api_key=GROQ_API_KEY)
    text_chunks = [c for c in chunks
                   if (c.chunk_type or "text").lower() != "image"]
    total_chars = sum(len(c.content or "") for c in text_chunks)
    use_batching = total_chars >= BATCH_THRESHOLD

    if use_batching:
        total_batches = (len(text_chunks) + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"[groq] Long document ({total_chars:,} chars) -> batched: "
              f"{len(text_chunks)} chunks -> {total_batches} batch(es) "
              f"(BATCH_SIZE={BATCH_SIZE}, model={GROQ_MODEL})")
    else:
        print(f"[groq] Short document ({total_chars:,} chars) -> single-call "
              f"(model={GROQ_MODEL})")

    batch_results: list[list[dict]] = []

    if not use_batching:
        full_text = _build_batch_text(text_chunks, title=title)
        print(f"  [groq] Sending full document ({len(full_text):,} chars) ...")
        concepts = _call_groq(client, full_text, "single-call")
        print(f"  [groq] -> {len(concepts)} concepts extracted.")
        batch_results.append(concepts)
    else:
        total_batches = (len(text_chunks) + BATCH_SIZE - 1) // BATCH_SIZE
        for batch_idx in range(total_batches):
            batch_chunks = text_chunks[
                batch_idx * BATCH_SIZE : (batch_idx + 1) * BATCH_SIZE
            ]
            batch_label = f"batch {batch_idx + 1}/{total_batches}"
            batch_text  = _build_batch_text(
                batch_chunks,
                title=title if batch_idx == 0 else "",
            )
            print(f"  [groq] Sending {batch_label} "
                  f"(chunks {batch_chunks[0].chunk_index}–"
                  f"{batch_chunks[-1].chunk_index}, "
                  f"{len(batch_text):,} chars) ...")
            concepts = _call_groq(client, batch_text, batch_label)
            print(f"  [groq] {batch_label} -> {len(concepts)} concepts extracted.")
            batch_results.append(concepts)

    merged    = _merge_batches(batch_results)
    raw_total = sum(len(b) for b in batch_results)
    print(f"[groq] Merged: {len(merged)} unique concepts "
          f"({raw_total} total, {raw_total - len(merged)} duplicates removed).")
    return merged


# ---------------------------------------------------------------------------
# Step 3: Save concepts + link to files
# ---------------------------------------------------------------------------

def save_concepts(
    concepts:    list[dict],
    course_name: str,
    user_id:     int,
    file_ids:    list[str],
) -> tuple[int, int]:
    """
    Upsert course, insert new concepts (with aliases + concept_type),
    link all course concepts to the uploaded files via concept_files,
    and enroll the user.
    Returns (course_id, n_inserted).
    """
    engine = create_engine(CONCEPT_DB_URL)
    with Session(engine) as session:

        # Upsert course
        course = session.query(Course).filter(Course.name == course_name).first()
        if course is None:
            course = Course(name=course_name)
            session.add(course)
            session.flush()
            print(f"[concept-db] Created course '{course_name}' (id={course.id}).")
        else:
            print(f"[concept-db] Reusing course '{course_name}' (id={course.id}).")

        course_id = course.id

        # Existing normalised names for this course
        existing = {
            _norm(row.name)
            for row in session.query(Concept.name)
                               .filter(Concept.course_id == course_id)
        }

        # Insert new concepts
        inserted = 0
        for item in concepts:
            if _norm(item["name"]) in existing:
                continue
            c = Concept(
                course_id    = course_id,
                name         = item["name"],
                difficulty   = item["difficulty"],
                aliases      = item["aliases"],
                concept_type = item["type"],
            )
            session.add(c)
            session.flush()
            existing.add(_norm(item["name"]))
            inserted += 1

        # Link ALL concepts in this course to the uploaded files
        all_concept_ids = [
            row.id for row in
            session.query(Concept.id).filter(Concept.course_id == course_id)
        ]
        for cid in all_concept_ids:
            for fid in file_ids:
                exists = session.execute(text("""
                    SELECT 1 FROM concept_files
                    WHERE concept_id = :cid AND file_id = :fid
                """), {"cid": cid, "fid": fid}).fetchone()
                if not exists:
                    session.execute(text("""
                        INSERT INTO concept_files (concept_id, file_id)
                        VALUES (:cid, :fid)
                    """), {"cid": cid, "fid": fid})

        # Enroll user
        user = session.get(User, user_id)
        if user is None:
            print(f"[concept-db] WARNING: user_id={user_id} not found, "
                  "skipping enrollment.")
        else:
            enrollment = session.get(CourseEnrollment, (user_id, course_id))
            if enrollment is None:
                session.add(CourseEnrollment(user_id=user_id, course_id=course_id))
                print(f"[concept-db] Enrolled user {user_id} in course {course_id}.")
            else:
                print(f"[concept-db] User {user_id} already enrolled.")

        session.commit()

    skipped = len(concepts) - inserted
    print(f"[concept-db] {inserted} new concepts inserted, {skipped} skipped.")
    return course_id, inserted


# ---------------------------------------------------------------------------
# Public API — called by the backend
# ---------------------------------------------------------------------------

def extract_and_store(
    file_ids:    list[str],
    course_name: str,
    user_id:     int,
    dry_run:     bool = False,
) -> dict:
    """
    Full pipeline for one or more files.
    Fetches chunks, extracts concepts (adaptive batching), saves to DB.
    Returns {"course_id": int, "n_inserted": int, "n_concepts": int}
    """
    print(f"\n{'='*60}")
    print(f"  Concept Extractor")
    print(f"  Course  : {course_name}")
    print(f"  User    : {user_id}")
    print(f"  Files   : {file_ids}")
    print(f"  Model   : {GROQ_MODEL}")
    print(f"  Batching: threshold={BATCH_THRESHOLD:,} chars, "
          f"batch_size={BATCH_SIZE} chunks")
    print(f"{'='*60}\n")

    file_results = fetch_chunks_for_files(file_ids)
    if not file_results:
        print("ERROR: No files found.", file=sys.stderr)
        return {"course_id": None, "n_inserted": 0, "n_concepts": 0}

    # Combine all chunks from all files into one pool for extraction
    resolved_file_ids: list[str] = []
    all_chunks:        list      = []
    combined_title = ""
    for fid, chunks, title in file_results:
        resolved_file_ids.append(fid)
        all_chunks.extend(chunks)
        combined_title = combined_title or title

    print(f"\n=== Extracting concepts ===")
    concepts = extract_concepts_from_chunks(all_chunks, title=combined_title)

    if dry_run:
        print("[dry-run] Skipping DB write.")
        return {"course_id": None, "n_inserted": 0, "n_concepts": len(concepts)}

    print(f"\n=== Saving to DB ===")
    course_id, n_inserted = save_concepts(
        concepts, course_name, user_id, resolved_file_ids
    )
    return {
        "course_id": course_id,
        "n_inserted": n_inserted,
        "n_concepts": len(concepts),
    }


# ---------------------------------------------------------------------------
# Standalone entry point (.env-based)
# ---------------------------------------------------------------------------

def main() -> None:
    course_name  = _optional("COURSE_NAME") or _require("COURSE_NAME")
    eppo_user_id = int(_optional("EPPO_USER_ID") or _require("EPPO_USER_ID"))
    file_id      = _optional("FILE_ID")
    file_name    = _optional("FILE_NAME")

    if not file_id and not file_name:
        print("ERROR: Set FILE_ID or FILE_NAME in .env", file=sys.stderr)
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  Concept Extractor  (standalone)")
    print(f"  Course          : {course_name}")
    print(f"  User ID         : {eppo_user_id}")
    print(f"  File            : {file_id or file_name}")
    print(f"  Model           : {GROQ_MODEL}")
    print(f"  Batch threshold : {BATCH_THRESHOLD:,} chars")
    print(f"  Max chars/call  : {MAX_CHARS:,}")
    print(f"  Dry run         : {DRY_RUN}")
    print(f"{'='*60}\n")

    resolved_id, chunks, title = fetch_chunks_single(
        file_id=file_id, file_name=file_name
    )

    print("\n=== Extracting concepts ===")
    concepts = extract_concepts_from_chunks(chunks, title=title)

    # Summary table
    type_counts: dict[str, int] = {}
    for c in concepts:
        type_counts[c["type"]] = type_counts.get(c["type"], 0) + 1

    print("\nExtracted concepts:")
    for i, c in enumerate(concepts, 1):
        bar     = "#" * c["difficulty"] + "-" * (5 - c["difficulty"])
        aliases = f"  aka: {', '.join(c['aliases'])}" if c["aliases"] else ""
        print(f"  {i:>3}. [{bar}] diff={c['difficulty']}  "
              f"[{c['type']:<22}]  {c['name']}{aliases}")

    print(f"\nConcept type breakdown:")
    for ctype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {ctype:<24} {count}")

    if DRY_RUN:
        print("\n[dry-run] Skipping database upload.")
        return

    print("\n=== Saving to DB ===")
    course_id, n_inserted = save_concepts(
        concepts, course_name, eppo_user_id, [resolved_id]
    )
    print(f"\nDone. course_id={course_id}, {n_inserted} concepts uploaded.")


if __name__ == "__main__":
    main()