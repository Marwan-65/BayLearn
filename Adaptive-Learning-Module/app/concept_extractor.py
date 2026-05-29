"""
concept_extractor.py
====================
Pipeline that:
  1. Reads all configuration from a .env file (no CLI arguments needed).
  2. Connects to the Input-Parsing-Module PostgreSQL database and pulls all
     chunks for a given file (FILE_ID or FILE_NAME).
  3. Extracts concepts using an adaptive strategy:
       - Short documents (< BATCH_THRESHOLD chars) → single Groq call.
       - Long documents (>= BATCH_THRESHOLD chars) → chunk-batched calls,
         results merged and deduplicated. This avoids paying the system-prompt
         overhead on every batch for documents that fit comfortably in one call,
         while still getting focused-context extraction on long documents where
         a single-pass model's attention degrades on early content.
  4. Inserts the merged concepts into the Adaptive-Learning-Module
     PostgreSQL database under the specified COURSE_NAME.

Supported domains (primary → secondary):
  Primary  : Computer Science, Computer Engineering, Software Engineering
  Secondary: Electrical Engineering, Communications, Embedded Systems,
             Cybersecurity, Cloud Computing, Machine Learning / AI, Physics
             (as it appears in CE curricula), Mathematics

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
    GROQ_MODEL          — Groq model id  (default: llama-3.3-70b-versatile)
    MAX_CHARS           — Max characters per Groq call (default: 40000)
    BATCH_SIZE          — Chunks per call when batching (default: 10)
    BATCH_THRESHOLD     — Char count above which batching is used (default: 40000)
    DRY_RUN             — Set to "true" to skip writing to the concept DB

─── Schema migration (run once on your Supabase instance) ────────────────────
    ALTER TABLE concepts
        ADD COLUMN IF NOT EXISTS aliases      JSONB NOT NULL DEFAULT '[]';
    ALTER TABLE concepts
        ADD COLUMN IF NOT EXISTS concept_type TEXT  NOT NULL DEFAULT 'unknown';
──────────────────────────────────────────────────────────────────────────────

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
GROQ_MODEL      = _optional("GROQ_MODEL", "llama-3.3-70b-versatile")
MAX_CHARS       = int(_optional("MAX_CHARS", "40000"))
BATCH_SIZE      = int(_optional("BATCH_SIZE", "10"))
# Documents shorter than this are sent in a single Groq call to avoid paying
# the system-prompt overhead on every batch. Documents at or above this
# threshold are batched so the model gets a focused context window per section.
BATCH_THRESHOLD = int(_optional("BATCH_THRESHOLD", "40000"))
DRY_RUN         = _optional("DRY_RUN", "false").lower() == "true"

# Valid concept types — used for type-scoped graph search in the dependency mapper.
# Stored on every concept so the matcher can restrict candidate retrieval to
# same-type nodes, dramatically reducing false-positive matches.
#
# Covers the full CE curriculum surface:
#   CS core, software engineering, electrical engineering, communications,
#   embedded systems, cybersecurity, cloud/distributed systems, ML/AI, math.
VALID_CONCEPT_TYPES = {
    "algorithm",            # any procedure or method: sorting, ML training, routing
    "data_structure",       # organisational abstractions: heap, trie, register file
    "paradigm",             # design / engineering / programming approaches
    "theorem_or_property",  # proven results, laws, principles: Nyquist, Ohm, master theorem
    "mathematical_concept", # pure/applied math: linear algebra, probability, Fourier analysis
    "hardware_concept",     # circuits, microarchitecture, embedded, digital logic, FPGA
    "system_concept",       # OS, cloud, distributed systems, virtualisation, RTOS
    "protocol_or_standard", # networking, communication, security protocols and standards
    "security_concept",     # cryptography, vulnerabilities, authentication, attack models
    "language_concept",     # PL, compiler, software-engineering, type systems
}

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

    id           = Column(Integer, primary_key=True)
    course_id    = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    name         = Column(String, nullable=False)
    difficulty   = Column(Integer, nullable=False)
    # New columns — require the migration in the module docstring
    aliases      = Column(JSON, nullable=False, default=list)
    concept_type = Column(String, nullable=False, default="unknown")

    course = relationship("Course", back_populates="concepts")


class CourseEnrollment(ConceptBase):
    __tablename__ = "course_enrollments"

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
# Step 2: Extract concepts — chunk-batched, then merged
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = textwrap.dedent("""\
    You are an expert engineering educator with deep knowledge of Computer
    Engineering, Computer Science, Electrical Engineering, Communications,
    Embedded Systems, Cybersecurity, Cloud Computing, and Applied Mathematics.

    Extract all academic concepts from a university-level engineering course
    document that a student must master and may be assessed on.

    ── NAMING RULES (these feed a concept dependency graph) ──────────────
    • Use standard textbook / IEEE / ACM terminology.
      CORRECT: "depth-first search"              WRONG: "the DFS thing"
      CORRECT: "pulse-width modulation"          WRONG: "PWM technique"
      CORRECT: "advanced encryption standard"    WRONG: "AES encryption"
    • Singular form, all lowercase.
      CORRECT: "binary search tree"              WRONG: "Binary Search Trees"
    • Canonical name must be the FULL name, not the acronym.
      Put the acronym in aliases instead.
      CORRECT: "dynamic programming"             WRONG: "DP"
      CORRECT: "phase-locked loop"               WRONG: "PLL"
    • Be specific — one concept per teachable unit.
      CORRECT: "merge sort"                      WRONG: "sorting algorithms"
      CORRECT: "Dijkstra's algorithm"            WRONG: "shortest path algorithms"
      CORRECT: "interrupt service routine"       WRONG: "interrupts"
      CORRECT: "quadrature amplitude modulation" WRONG: "modulation techniques"
    • If two phrasings mean the same concept, emit only the canonical one
      and put alternatives in aliases.

    ── GRANULARITY RULE ──────────────────────────────────────────────────
    Extract at the level of a single lecture topic or textbook section title.
    Too broad:  "graph algorithms", "signal processing", "network security"
    Too narrow: "incrementing a loop counter", "writing a register value"
    Just right: "breadth-first search", "discrete Fourier transform",
                "ARP poisoning", "priority inversion", "cache coherence
                protocol", "Q-learning", "Viterbi algorithm"

    ── DIFFICULTY SCALE ─────────────────────────────────────────────────
    Calibrated across CS, CE, and EE domains:

    1 — Definitional
        CS/CE : variable declaration, what is an algorithm, logic gates
        EE    : Ohm's law, what is a signal, voltage divider
        ML    : what is a neuron, supervised vs unsupervised learning

    2 — Foundational
        CS/CE : recursion, big-O notation, linked list, binary search
        EE    : RC circuit analysis, Boolean algebra, sampling theorem
        ML    : gradient descent, linear regression, train/test split

    3 — Applied
        CS/CE : dynamic programming, hash table, graph traversal, mutex
        EE    : Fourier transform, PID controller, UART protocol, pipeline stages
        ML    : backpropagation, convolutional neural network, k-means clustering

    4 — Advanced
        CS/CE : amortized analysis, NP-completeness, memory-mapped I/O, TLS handshake
        EE    : phase-locked loop, OFDM, DMA controller, cache coherence
        ML    : attention mechanism, variational autoencoder, policy gradient

    5 — Expert
        CS/CE : computational complexity theory, type theory, distributed consensus
        EE    : VLSI design methodology, adaptive equalisation, formal verification
        ML    : meta-learning, neural architecture search, convergence proofs

    ── CONCEPT TYPES ────────────────────────────────────────────────────
    Assign the single most specific type that fits.

    "algorithm"
        Procedures and methods with defined steps.
        e.g. merge sort, Dijkstra's algorithm, backpropagation,
             Viterbi algorithm, RSA key generation, Needleman–Wunsch

    "data_structure"
        Ways of organising or storing data / state.
        e.g. red-black tree, bloom filter, register file, page table,
             neural network weight tensor (as a structure)

    "paradigm"
        High-level design, programming, or engineering approaches.
        e.g. object-oriented programming, divide and conquer,
             event-driven architecture, agile development,
             model-view-controller, test-driven development

    "theorem_or_property"
        Proven mathematical results, physical laws, or formal properties.
        e.g. master theorem, Nyquist–Shannon sampling theorem,
             Kirchhoff's voltage law, CAP theorem, pumping lemma,
             loop invariant, Shannon's channel capacity

    "mathematical_concept"
        Pure or applied mathematics as taught in an engineering context.
        e.g. eigenvalue decomposition, convolution, modular arithmetic,
             Bayes' theorem, Markov chain, z-transform, gradient vector

    "hardware_concept"
        Physical circuits, digital logic, microarchitecture, and embedded topics.
        e.g. pipeline hazard, cache replacement policy, interrupt service routine,
             field-programmable gate array, analog-to-digital converter,
             memory-mapped I/O, PWM, instruction set architecture

    "system_concept"
        OS, cloud, distributed, virtualisation, and RTOS concepts.
        e.g. virtual memory, process scheduling, containerisation,
             consensus algorithm, service mesh, deadlock, hypervisor

    "protocol_or_standard"
        Networking, communication, and interoperability protocols/standards.
        e.g. TCP three-way handshake, OFDM, I2C protocol,
             TLS certificate chain, IEEE 802.11 MAC, MQTT

    "security_concept"
        Cryptography, threat models, attack types, and defensive mechanisms.
        e.g. public-key cryptography, SQL injection, buffer overflow,
             zero-knowledge proof, ARP poisoning, access control list

    "language_concept"
        Programming language theory, compiler design, and software-engineering
        practices.
        e.g. static type checking, tail call optimisation, garbage collection,
             abstract syntax tree, dependency injection, design pattern

    ── OUTPUT FIELDS ────────────────────────────────────────────────────
    "name"       : canonical concept name (follow NAMING RULES exactly)
    "aliases"    : list of 0–3 well-known alternative names or acronyms
                   e.g. ["DFT", "discrete Fourier transform"]
    "difficulty" : integer 1–5 (use DIFFICULTY SCALE above)
    "type"       : exactly one value from CONCEPT TYPES above

    ── EXTRACTION RULES ─────────────────────────────────────────────────
    • Be exhaustive — extract EVERY concept a student must understand.
    • Do NOT extract meta-concepts (exam tips, study advice, logistics).
    • Do NOT extract proper nouns that are not concepts (people, institutions).
    • Do NOT duplicate — one canonical entry per concept; merge synonyms into aliases.
    • When the domain is ambiguous, prefer the engineering interpretation.
    • Return ONLY a valid JSON array. No markdown fences, no preamble, no explanation.

    ── EXAMPLE OUTPUT ───────────────────────────────────────────────────
    [
      {
        "name": "interrupt service routine",
        "aliases": ["ISR", "interrupt handler"],
        "difficulty": 3,
        "type": "hardware_concept"
      },
      {
        "name": "Nyquist-Shannon sampling theorem",
        "aliases": ["sampling theorem", "Nyquist theorem"],
        "difficulty": 3,
        "type": "theorem_or_property"
      },
      {
        "name": "public-key cryptography",
        "aliases": ["asymmetric cryptography", "asymmetric encryption"],
        "difficulty": 3,
        "type": "security_concept"
      },
      {
        "name": "backpropagation",
        "aliases": ["backprop", "reverse-mode automatic differentiation"],
        "difficulty": 3,
        "type": "algorithm"
      },
      {
        "name": "cache coherence protocol",
        "aliases": ["cache coherency"],
        "difficulty": 4,
        "type": "hardware_concept"
      }
    ]
""")


def _build_batch_text(chunks: list[Chunk], title: str = "") -> str:
    """Render a list of chunks into a single text block for one Groq call."""
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

    raw_output = response.choices[0].message.content.strip()

    # Strip accidental markdown fences
    if raw_output.startswith("```"):
        raw_output = raw_output.split("```")[1]
        if raw_output.startswith("json"):
            raw_output = raw_output[4:]
        raw_output = raw_output.rsplit("```", 1)[0]

    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        print(f"  [groq] WARNING: JSON parse error on {batch_label}: {exc}. Skipping batch.")
        return []

    validated: list[dict] = []
    for item in parsed:
        name = str(item.get("name", "")).strip().lower()
        if not name:
            continue

        difficulty = max(1, min(5, int(item.get("difficulty", 3))))

        raw_type = str(item.get("type", "unknown")).strip().lower()
        concept_type = raw_type if raw_type in VALID_CONCEPT_TYPES else "unknown"

        raw_aliases = item.get("aliases", [])
        aliases = [
            str(a).strip().lower()
            for a in (raw_aliases if isinstance(raw_aliases, list) else [])
            if str(a).strip()
        ]
        # Drop any alias that is identical to the canonical name
        aliases = [a for a in aliases if a != name]

        validated.append({
            "name":         name,
            "aliases":      aliases,
            "difficulty":   difficulty,
            "type":         concept_type,
        })

    return validated


# ---------------------------------------------------------------------------
# Merge logic
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    """Normalise a concept name for deduplication keying."""
    return " ".join(s.lower().split())


def _merge_batches(batch_results: list[list[dict]]) -> list[dict]:
    """
    Merge per-batch concept lists into a single deduplicated list.

    Deduplication key: normalised canonical name OR any alias that already
    exists as a known key.  On conflict:
      - aliases  : union of alias sets (duplicates removed)
      - difficulty: maximum across all occurrences
      - type     : first non-'unknown' value wins
    """
    # canonical_map: norm_name -> concept dict
    canonical_map: dict[str, dict] = {}
    # alias_index: norm_alias -> norm_name it belongs to
    alias_index: dict[str, str] = {}

    for batch in batch_results:
        for concept in batch:
            norm_name    = _norm(concept["name"])
            norm_aliases = [_norm(a) for a in concept["aliases"]]

            # Find if this concept already has an entry
            existing_key: Optional[str] = None
            if norm_name in canonical_map:
                existing_key = norm_name
            elif norm_name in alias_index:
                existing_key = alias_index[norm_name]
            else:
                for na in norm_aliases:
                    if na in canonical_map:
                        existing_key = na
                        break
                    if na in alias_index:
                        existing_key = alias_index[na]
                        break

            if existing_key is not None:
                # ── Merge into existing entry ──────────────────────────
                entry = canonical_map[existing_key]

                # Union aliases
                existing_norms = {_norm(a) for a in entry["aliases"]}
                for na, raw_a in zip(norm_aliases, concept["aliases"]):
                    if na not in existing_norms and na != existing_key:
                        entry["aliases"].append(raw_a)
                        existing_norms.add(na)
                        alias_index.setdefault(na, existing_key)

                # Keep hardest difficulty
                entry["difficulty"] = max(entry["difficulty"], concept["difficulty"])

                # First non-unknown type wins
                if entry["type"] == "unknown" and concept["type"] != "unknown":
                    entry["type"] = concept["type"]

            else:
                # ── Register new entry ────────────────────────────────
                entry = {
                    "name":       concept["name"],
                    "aliases":    list(dict.fromkeys(concept["aliases"])),  # preserve order, deduplicate
                    "difficulty": concept["difficulty"],
                    "type":       concept["type"],
                }
                canonical_map[norm_name] = entry
                alias_index[norm_name] = norm_name   # self-map for reverse lookups
                for na, raw_a in zip(norm_aliases, concept["aliases"]):
                    alias_index.setdefault(na, norm_name)

    return list(canonical_map.values())


def extract_concepts_from_chunks(chunks: list[Chunk], title: str = "") -> list[dict]:
    """
    Extract concepts using an adaptive strategy to minimise token overhead:

    - SHORT documents (total text < BATCH_THRESHOLD chars): assemble into a
      single string and send as one Groq call.  Avoids paying the system-prompt
      overhead on every batch when the document fits comfortably in one window.

    - LONG documents (total text >= BATCH_THRESHOLD chars): process in batches
      of BATCH_SIZE chunks, each as an independent Groq call.  The model gets a
      focused context window per section rather than one degraded pass over the
      full document where early content receives weaker attention.

    Results from all calls are merged and deduplicated by _merge_batches.
    """
    client = Groq(api_key=GROQ_API_KEY)

    # Filter image-only chunks — no text to extract
    text_chunks = [c for c in chunks if (c.chunk_type or "text").lower() != "image"]

    # Measure total document size to decide strategy
    total_chars = sum(len(c.content or "") for c in text_chunks)
    use_batching = total_chars >= BATCH_THRESHOLD

    if use_batching:
        total_batches = (len(text_chunks) + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"[groq] Long document ({total_chars:,} chars) → batched mode: "
              f"{len(text_chunks)} text chunks → {total_batches} batch(es) "
              f"(BATCH_SIZE={BATCH_SIZE}, model={GROQ_MODEL})")
    else:
        print(f"[groq] Short document ({total_chars:,} chars) → single-call mode "
              f"(model={GROQ_MODEL})")

    batch_results: list[list[dict]] = []

    if not use_batching:
        # ── Single call ────────────────────────────────────────────────────
        full_text = _build_batch_text(text_chunks, title=title)
        print(f"  [groq] Sending full document ({len(full_text):,} chars) …")
        concepts = _call_groq(client, full_text, "single-call")
        print(f"  [groq] → {len(concepts)} concepts extracted.")
        batch_results.append(concepts)

    else:
        # ── Batched calls ──────────────────────────────────────────────────
        total_batches = (len(text_chunks) + BATCH_SIZE - 1) // BATCH_SIZE
        for batch_idx in range(total_batches):
            batch_chunks = text_chunks[batch_idx * BATCH_SIZE : (batch_idx + 1) * BATCH_SIZE]
            batch_label  = f"batch {batch_idx + 1}/{total_batches}"

            # Include document title only on the first batch for context
            batch_text = _build_batch_text(
                batch_chunks,
                title=title if batch_idx == 0 else "",
            )

            print(f"  [groq] Sending {batch_label} "
                  f"(chunks {batch_chunks[0].chunk_index}–{batch_chunks[-1].chunk_index}, "
                  f"{len(batch_text):,} chars) …")

            concepts = _call_groq(client, batch_text, batch_label)
            print(f"  [groq] {batch_label} → {len(concepts)} concepts extracted.")
            batch_results.append(concepts)

    merged = _merge_batches(batch_results)
    raw_total = sum(len(b) for b in batch_results)
    print(f"[groq] Merged result: {len(merged)} unique concepts "
          f"(from {raw_total} total across all calls, "
          f"{raw_total - len(merged)} duplicates removed).")
    return merged


# ---------------------------------------------------------------------------
# Step 3: Upload concepts to the Adaptive-Learning DB
# ---------------------------------------------------------------------------

def upload_concepts(concepts: list[dict]) -> tuple[int, int]:
    """
    Upsert the course row, insert extracted concepts, and enroll EPPO_USER_ID.

    The `concept_type` field is stored on every concept so the dependency
    mapper can restrict candidate retrieval to same-type nodes when building
    the similarity graph (type-scoped search).

    Concepts already present for this course (same normalised name) are
    silently skipped. Returns (course_id, n_inserted).
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

        # ── Insert concepts (skip duplicates by normalised name) ───────────
        existing_names: set[str] = {
            _norm(row.name)
            for row in session.query(Concept.name)
                               .filter(Concept.course_id == course_id)
                               .all()
        }

        inserted = 0
        skipped  = 0
        for item in concepts:
            if _norm(item["name"]) in existing_names:
                skipped += 1
                continue
            session.add(Concept(
                course_id    = course_id,
                name         = item["name"],
                difficulty   = item["difficulty"],
                aliases      = item["aliases"],
                concept_type = item["type"],
            ))
            existing_names.add(_norm(item["name"]))
            inserted += 1

        # ── Enroll user (get-or-create) ────────────────────────────────────
        user = session.get(User, EPPO_USER_ID)
        if user is None:
            print(
                f"[concept-db] WARNING: user_id={EPPO_USER_ID} not found; "
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
    print(f"  Course          : {COURSE_NAME}")
    print(f"  User ID         : {EPPO_USER_ID}")
    print(f"  File            : {FILE_ID or FILE_NAME}")
    print(f"  Model           : {GROQ_MODEL}")
    print(f"  Batch threshold : {BATCH_THRESHOLD:,} chars  "
          f"(below = single call, above = {BATCH_SIZE} chunks/batch)")
    print(f"  Max chars/call  : {MAX_CHARS:,}")
    print(f"  Dry run         : {DRY_RUN}")
    print(f"{'='*60}\n")

    # Step 1
    print("=== Step 1: Fetching chunks ===")
    _, chunks, title = fetch_chunks()

    # Step 2
    print("\n=== Step 2: Extracting concepts (chunk-batched) ===")
    concepts = extract_concepts_from_chunks(chunks, title=title)

    # Summary table
    type_counts: dict[str, int] = {}
    for c in concepts:
        type_counts[c["type"]] = type_counts.get(c["type"], 0) + 1

    print("\nExtracted concepts:")
    for i, c in enumerate(concepts, 1):
        bar     = "█" * c["difficulty"] + "░" * (5 - c["difficulty"])
        aliases = f"  aka: {', '.join(c['aliases'])}" if c["aliases"] else ""
        print(f"  {i:>3}. [{bar}] diff={c['difficulty']}  [{c['type']:<22}]  "
              f"{c['name']}{aliases}")

    print(f"\nConcept type breakdown:")
    for ctype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {ctype:<24} {count}")

    # Step 3
    if DRY_RUN:
        print("\n[dry-run] Skipping database upload.")
    else:
        print("\n=== Step 3: Uploading concepts to concept DB ===")
        course_id, n_inserted = upload_concepts(concepts)
        print(f"\nDone. course_id={course_id}, {n_inserted} concepts uploaded.")


if __name__ == "__main__":
    main()