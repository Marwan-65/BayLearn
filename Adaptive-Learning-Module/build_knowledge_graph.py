"""
build_knowledge_graph.py
========================
One-time setup script. Downloads the metacademy-content repository and
populates two tables in the Adaptive-Learning-Module database:

  knowledge_nodes — canonical concept nodes (name, description, type, aliases)
  knowledge_edges — prerequisite edges  (from_node MUST be mastered before to_node)

Run this ONCE before using concept_mapper.py.
It is safe to re-run — existing rows are skipped.

Usage:
    python build_knowledge_graph.py

─── SQL to run on Supabase FIRST ─────────────────────────────────────────────

    CREATE TABLE IF NOT EXISTS knowledge_nodes (
        id           SERIAL PRIMARY KEY,
        name         TEXT    NOT NULL,
        description  TEXT,
        aliases      JSONB   NOT NULL DEFAULT '[]',
        concept_type TEXT    NOT NULL DEFAULT 'unknown',
        source       TEXT    NOT NULL,
        source_id    TEXT,
        UNIQUE (source, source_id)
    );

    CREATE TABLE IF NOT EXISTS knowledge_edges (
        id           SERIAL  PRIMARY KEY,
        from_node_id INTEGER NOT NULL
                        REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
        to_node_id   INTEGER NOT NULL
                        REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
        source       TEXT    NOT NULL,
        UNIQUE (from_node_id, to_node_id)
    );

    CREATE TABLE IF NOT EXISTS concept_node_mappings (
        concept_id   INTEGER NOT NULL REFERENCES concepts(id)        ON DELETE CASCADE,
        node_id      INTEGER NOT NULL REFERENCES knowledge_nodes(id)  ON DELETE CASCADE,
        confidence   FLOAT   NOT NULL,
        match_type   TEXT    NOT NULL
                        CHECK (match_type IN ('exact_name','exact_alias','semantic')),
        PRIMARY KEY (concept_id, node_id)
    );

──────────────────────────────────────────────────────────────────────────────

About the data format (metacademy-content flat-file DB):
    Each concept lives in concepts/<tag>/ with plain-text files inside:
      title.txt        → single-line concept name shown to users
      summary.txt      → 2-3 sentence description
      dependencies.txt → list of prerequisite concept tags
      id.txt           → stable unique id (different from the dir tag)
      see-also.txt     → related concepts (treated as soft aliases)

    dependencies.txt format (one dependency per blank-line-separated block):
        tag: covariance
        reason: the covariance matrix is a PSD matrix.
        shortcut: 1

    Edge meaning: tag in dependencies.txt → this concept
    (i.e. the dependency must be mastered BEFORE this concept)

Required .env key:
    CONCEPT_DB_URL  — same connection string as concept_extractor.py

Optional .env keys:
    METACADEMY_ZIP  — path to a locally downloaded metacademy-content .zip
                      (skips the GitHub download)
"""

from __future__ import annotations

import io
import os
import re
import sys
import zipfile
from pathlib import Path

import requests
from dotenv import load_dotenv
from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    func,
)
from sqlalchemy.orm import declarative_base, Session

load_dotenv(Path(__file__).parent / ".env")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONCEPT_DB_URL = os.environ.get("CONCEPT_DB_URL", "").strip()
if not CONCEPT_DB_URL:
    print("ERROR: CONCEPT_DB_URL not set in .env", file=sys.stderr)
    sys.exit(1)

METACADEMY_ZIP = os.environ.get("METACADEMY_ZIP", "").strip()

# metacademy-CONTENT repo — this is where the concept data lives.
# (metacademy-application is the web app code and has no concept data.)
_CONTENT_URL = (
    "https://github.com/metacademy/metacademy-content"
    "/archive/refs/heads/master.zip"
)

# ---------------------------------------------------------------------------
# SQLAlchemy models
# ---------------------------------------------------------------------------

Base = declarative_base()


class KnowledgeNode(Base):
    __tablename__ = "knowledge_nodes"
    __table_args__ = (UniqueConstraint("source", "source_id"),)

    id           = Column(Integer, primary_key=True)
    name         = Column(String,  nullable=False)
    description  = Column(Text)
    aliases      = Column(JSON,    nullable=False, default=list)
    concept_type = Column(String,  nullable=False, default="unknown")
    source       = Column(String,  nullable=False)
    source_id    = Column(String)


class KnowledgeEdge(Base):
    __tablename__ = "knowledge_edges"
    __table_args__ = (UniqueConstraint("from_node_id", "to_node_id"),)

    id           = Column(Integer, primary_key=True)
    from_node_id = Column(Integer, ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False)
    to_node_id   = Column(Integer, ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False)
    source       = Column(String,  nullable=False)


# ---------------------------------------------------------------------------
# Concept-type inference
# Pattern rules ordered by specificity — first match wins.
# Types only need to be directionally correct; the cross-encoder in
# concept_mapper.py corrects most errors during matching.
# ---------------------------------------------------------------------------

_TYPE_RULES: list[tuple[str, list[str]]] = [
    ("security_concept", [
        "cryptograph", "encrypt", "decrypt", "cipher", "authentication",
        "authorization", "vulnerability", "exploit", "injection", "ssl",
        "tls", "firewall", "intrusion", "malware", "hash function",
        "zero-knowledge", "public key", "private key",
    ]),
    ("protocol_or_standard", [
        " protocol", "tcp", "udp", "http", "ip address", "ethernet",
        "i2c", "spi", "uart", "can bus", "bluetooth", "ieee 802",
        "modulation", "ofdm", "cdma",
    ]),
    ("hardware_concept", [
        "circuit", "microcontroller", "microprocessor", "fpga",
        "pipeline hazard", "cache line", "register file", "instruction set",
        "interrupt", "dma", "memory-mapped", "analog-to-digital",
        "digital-to-analog", "pwm", "digital logic", "flip-flop",
        "logic gate", "bus arbitration", "embedded system",
        "cpu architecture", "gpu architecture", "von neumann",
    ]),
    ("system_concept", [
        "operating system", "kernel", " process ", " thread ", "scheduler",
        "virtual memory", "page fault", "deadlock", "mutex", "semaphore",
        "distributed system", "cloud computing", "container",
        "hypervisor", "file system", "inter-process", "memory management",
    ]),
    ("data_structure", [
        " tree", "linked list", "hash table", "hash map", " heap",
        " queue", " stack", " trie", "bloom filter", "skip list",
        "priority queue", "adjacency matrix", "adjacency list",
        "binary tree", "b-tree", "red-black",
    ]),
    ("algorithm", [
        "algorithm", " sort", "graph traversal", "pathfinding",
        "backpropagation", "gradient descent", "k-means",
        "dynamic programming", "greedy", "divide and conquer",
        "convex hull", "maximum flow", "minimum spanning",
    ]),
    ("mathematical_concept", [
        "fourier", "laplace", "z-transform", "eigenvalue", "eigenvector",
        "linear algebra", "convolution", "probability distribution",
        "markov chain", "bayesian", "stochastic process",
        "calculus", "derivative", "integral", "modular arithmetic",
        "combinatorics", "graph theory", "set theory",
    ]),
    ("theorem_or_property", [
        "theorem", " lemma", "kirchhoff", "nyquist", "shannon capacity",
        "cap theorem", "pumping lemma", "loop invariant",
        "master theorem", " law of ", "invariant", "bayes' theorem",
    ]),
    ("paradigm", [
        "object-oriented", "functional programming", "concurrent programming",
        "event-driven", "reactive programming", "design pattern",
        "model-view", "aspect-oriented", "test-driven",
    ]),
    ("language_concept", [
        "type system", "type checking", "garbage collection", "compiler",
        "polymorphism", "generics", "closure", "lambda calculus",
        "abstract syntax", "bytecode", "jit compilation",
        "memory model", "concurrency model",
    ]),
]


def _infer_type(name: str, description: str = "") -> str:
    haystack = (name + " " + (description or "")).lower()
    for concept_type, keywords in _TYPE_RULES:
        if any(kw in haystack for kw in keywords):
            return concept_type
    return "unknown"


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def _get_zip_bytes() -> bytes:
    if METACADEMY_ZIP:
        p = Path(METACADEMY_ZIP)
        if not p.exists():
            print(f"ERROR: METACADEMY_ZIP path not found: {p}", file=sys.stderr)
            sys.exit(1)
        print(f"[data] Using local archive: {p}")
        return p.read_bytes()

    print(f"[data] Downloading metacademy-content from GitHub …")
    try:
        resp = requests.get(_CONTENT_URL, timeout=180, stream=True)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"ERROR: Download failed: {exc}", file=sys.stderr)
        print("  Set METACADEMY_ZIP=<path> in .env to use a local copy.", file=sys.stderr)
        sys.exit(1)

    chunks: list[bytes] = []
    total = 0
    for chunk in resp.iter_content(chunk_size=65_536):
        chunks.append(chunk)
        total += len(chunk)
        print(f"\r  {total / 1_048_576:.1f} MB downloaded", end="", flush=True)
    print()
    data = b"".join(chunks)
    print(f"[data] Complete ({len(data) / 1_048_576:.1f} MB).")
    return data


# ---------------------------------------------------------------------------
# Flat-file parser
#
# The metacademy-content repo uses a custom plain-text format.
# Each concept lives at:
#   metacademy-content-master/concepts/<tag>/
# with individual text files inside for each field.
#
# dependencies.txt contains blocks separated by blank lines, each block
# being a set of "key: value" lines.  The relevant key is "tag".
# ---------------------------------------------------------------------------

def _read_zip_file(zf: zipfile.ZipFile, path: str) -> str:
    """Read a file from the zip, return empty string if missing."""
    try:
        return zf.read(path).decode("utf-8", errors="replace").strip()
    except KeyError:
        return ""


def _parse_deps_txt(raw: str) -> list[str]:
    """
    Parse a dependencies.txt file and return a list of prerequisite tag strings.

    Format (blank-line-separated blocks of key: value pairs):
        tag: covariance
        reason: the covariance matrix is a PSD matrix.
        shortcut: 1

        tag: positive-definite-matrices
    """
    tags: list[str] = []
    for block in re.split(r"\n\s*\n", raw):
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("#"):
                continue
            if line.lower().startswith("tag:"):
                tag = line[4:].strip()
                if tag:
                    tags.append(tag)
    return tags


def _parse_see_also_txt(raw: str) -> list[str]:
    """
    Extract concept tags from see-also.txt (Textile-like format).
    Links look like: "label":concept_tag
    """
    return re.findall(r'"[^"]+":([a-zA-Z0-9_\-]+)', raw)


def parse_metacademy(zip_bytes: bytes) -> tuple[list[dict], list[tuple[str, str]]]:
    """
    Parse the metacademy-content ZIP archive.

    Returns:
        nodes : list of dicts — {tag, name, description, aliases}
        edges : list of (prerequisite_tag, dependent_tag) tuples
    """
    nodes: list[dict] = []
    edges: list[tuple[str, str]] = []

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        all_names = zf.namelist()

        # The archive root is "metacademy-content-master/"
        # Concept directories are: metacademy-content-master/concepts/<tag>/
        concept_dirs: set[str] = set()
        for name in all_names:
            # Match paths like: metacademy-content-master/concepts/backpropagation/title.txt
            m = re.match(r"([^/]+/concepts/)([^/]+)/", name)
            if m:
                concept_dirs.add(m.group(1) + m.group(2) + "/")

        print(f"[parse] Found {len(concept_dirs)} concept directories in archive.")

        for concept_dir in sorted(concept_dirs):
            # The tag is the last non-empty component of the directory path
            tag = concept_dir.rstrip("/").split("/")[-1]

            name        = _read_zip_file(zf, concept_dir + "title.txt")
            description = _read_zip_file(zf, concept_dir + "summary.txt")
            deps_raw    = _read_zip_file(zf, concept_dir + "dependencies.txt")
            see_raw     = _read_zip_file(zf, concept_dir + "see-also.txt")

            if not name:
                # Fall back to humanising the tag itself
                name = tag.replace("_", " ").replace("-", " ")

            # Soft aliases from see-also (related concept tags converted to readable names)
            see_also_tags = _parse_see_also_txt(see_raw)
            aliases = [t.replace("_", " ").replace("-", " ").lower() for t in see_also_tags[:4]]

            nodes.append({
                "tag":         tag,
                "name":        name.lower().strip(),
                "description": description[:1000] if description else None,
                "aliases":     aliases,
            })

            for prereq_tag in _parse_deps_txt(deps_raw):
                edges.append((prereq_tag, tag))  # prereq → this concept

    print(f"[parse] Parsed {len(nodes)} nodes, {len(edges)} raw dependency edges.")
    return nodes, edges


# ---------------------------------------------------------------------------
# DB insertion
# ---------------------------------------------------------------------------

def build_graph() -> None:
    zip_bytes = _get_zip_bytes()

    print("\n=== Parsing archive ===")
    raw_nodes, raw_edges = parse_metacademy(zip_bytes)

    if not raw_nodes:
        print(
            "ERROR: No concept nodes found.\n"
            "  Make sure METACADEMY_ZIP points to the metacademy-CONTENT repo,\n"
            "  not the metacademy-application repo.",
            file=sys.stderr,
        )
        sys.exit(1)

    engine = create_engine(CONCEPT_DB_URL)

    print("\n=== Writing nodes to database ===")
    with Session(engine) as session:
        # Pre-load existing source_ids to avoid per-row queries
        existing: dict[str, int] = {
            sid: dbid
            for sid, dbid in session.query(
                KnowledgeNode.source_id, KnowledgeNode.id
            ).filter(KnowledgeNode.source == "metacademy").all()
        }

        tag_to_db_id: dict[str, int] = dict(existing)
        inserted_nodes = 0

        for raw in raw_nodes:
            tag = raw["tag"]
            if tag in existing:
                continue  # already in DB from a previous run

            concept_type = _infer_type(raw["name"], raw["description"] or "")

            node = KnowledgeNode(
                name         = raw["name"],
                description  = raw["description"],
                aliases      = raw["aliases"],
                concept_type = concept_type,
                source       = "metacademy",
                source_id    = tag,
            )
            session.add(node)
            session.flush()
            tag_to_db_id[tag] = node.id
            inserted_nodes += 1

        session.commit()
        skipped_nodes = len(raw_nodes) - inserted_nodes
        print(f"[db] Nodes: {inserted_nodes} inserted, {skipped_nodes} already existed.")

        print("\n=== Writing edges to database ===")
        inserted_edges = 0
        skipped_edges  = 0

        # Pre-load existing edges to avoid per-row queries
        existing_edges: set[tuple[int, int]] = {
            (f, t)
            for f, t in session.query(
                KnowledgeEdge.from_node_id, KnowledgeEdge.to_node_id
            ).all()
        }

        for prereq_tag, dependent_tag in raw_edges:
            from_id = tag_to_db_id.get(prereq_tag)
            to_id   = tag_to_db_id.get(dependent_tag)

            if not from_id or not to_id or from_id == to_id:
                skipped_edges += 1
                continue
            if (from_id, to_id) in existing_edges:
                skipped_edges += 1
                continue

            session.add(KnowledgeEdge(
                from_node_id = from_id,
                to_node_id   = to_id,
                source       = "metacademy",
            ))
            existing_edges.add((from_id, to_id))
            inserted_edges += 1

        session.commit()
        print(f"[db] Edges: {inserted_edges} inserted, {skipped_edges} skipped.")

    # ── Final summary ─────────────────────────────────────────────────────
    with Session(engine) as session:
        total_nodes = session.query(KnowledgeNode).count()
        total_edges = session.query(KnowledgeEdge).count()
        type_rows = (
            session.query(KnowledgeNode.concept_type, func.count(KnowledgeNode.id))
            .group_by(KnowledgeNode.concept_type)
            .order_by(func.count(KnowledgeNode.id).desc())
            .all()
        )

    print(f"\n[done] Graph totals: {total_nodes} nodes, {total_edges} edges.")
    print("\nNode type breakdown:")
    for ctype, count in type_rows:
        print(f"  {ctype:<26} {count}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"  Knowledge Graph Builder")
    print(f"  Source : metacademy-content (GitHub)")
    print(f"{'='*60}\n")
    build_graph()