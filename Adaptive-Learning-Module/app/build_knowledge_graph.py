"""
build_knowledge_graph.py
========================
One-time setup script. Downloads the metacademy-content repository and
populates two tables in the Adaptive-Learning-Module database:

  knowledge_nodes — canonical concept nodes (name, description, type, aliases)
  knowledge_edges — prerequisite edges  (from_node MUST be mastered before to_node)

Run this ONCE before using concept_mapper.py.
It is safe to re-run — existing rows are skipped via UNIQUE constraints.

Usage:
    python build_knowledge_graph.py

Schema note:
    knowledge_nodes.id  — SERIAL integer (not UUID)
    knowledge_edges.id  — SERIAL integer (not UUID)
    These tables are populated by this script and concept_mapper.py only.
    concept_node_mappings.concept_id is VARCHAR (UUID) since concepts.id is UUID.
    concept_node_mappings.node_id    is INTEGER since knowledge_nodes.id is SERIAL.

Required .env key:
    CONCEPT_DB_URL

Optional .env keys:
    METACADEMY_ZIP  — path to a locally downloaded metacademy-content .zip
    ACM_CCS_PATH    — path to the ACM CCS XML file
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
    Column, Float, ForeignKey, Integer, JSON,
    String, Text, UniqueConstraint,
    create_engine, func,
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
ACM_CCS_PATH   = os.environ.get("ACM_CCS_PATH",   "").strip()

_CONTENT_URL = (
    "https://github.com/metacademy/metacademy-content"
    "/archive/refs/heads/master.zip"
)

# ---------------------------------------------------------------------------
# ORM models
# knowledge_nodes and knowledge_edges use integer serial PKs.
# concept_node_mappings.concept_id is VARCHAR (UUID) — concepts.id is UUID.
# ---------------------------------------------------------------------------

Base = declarative_base()


class KnowledgeNode(Base):
    __tablename__ = "knowledge_nodes"
    __table_args__ = (UniqueConstraint("source", "source_id"),)

    id           = Column(Integer, primary_key=True, autoincrement=True)
    name         = Column(String,  nullable=False)
    description  = Column(Text)
    aliases      = Column(JSON,    nullable=False, default=list)
    concept_type = Column(String,  nullable=False, default="unknown")
    source       = Column(String,  nullable=False)
    source_id    = Column(String)


class KnowledgeEdge(Base):
    __tablename__ = "knowledge_edges"
    __table_args__ = (UniqueConstraint("from_node_id", "to_node_id"),)

    id           = Column(Integer, primary_key=True, autoincrement=True)
    from_node_id = Column(Integer, ForeignKey("knowledge_nodes.id",
                                               ondelete="CASCADE"),
                          nullable=False)
    to_node_id   = Column(Integer, ForeignKey("knowledge_nodes.id",
                                               ondelete="CASCADE"),
                          nullable=False)
    source       = Column(String, nullable=False)


# ---------------------------------------------------------------------------
# Concept-type inference
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
# ACM CCS 2012
# ---------------------------------------------------------------------------

_ACM_ROOT_TYPE: dict[str, str] = {
    "10010583": "hardware_concept",
    "10010520": "system_concept",
    "10011007": "language_concept",
    "10002978": "security_concept",
    "10003033": "protocol_or_standard",
    "10003752": "theorem_or_property",
    "10010147": "algorithm",
    "10002950": "mathematical_concept",
    "10002951": "system_concept",
    "10010405": "system_concept",
    "10002944": "unknown",
    "10003120": "unknown",
    "10003456": "unknown",
}


def parse_acm_ccs(xml_path: str) -> tuple[list[dict], list[tuple[str, str]]]:
    import xml.etree.ElementTree as ET
    SKOS = "http://www.w3.org/2004/02/skos/core#"
    RDF  = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    _SKIP_ROOTS = {"10002944", "10003456", "10003120"}

    tree    = ET.parse(xml_path)
    root_el = tree.getroot()
    nodes: list[dict]            = []
    edges: list[tuple[str, str]] = []

    for concept in root_el.findall(f"{{{SKOS}}}Concept"):
        cid   = concept.get(f"{{{RDF}}}about", "").strip()
        depth = cid.count(".")
        if depth == 0 or not cid:
            continue
        root_id = cid.split(".")[0]
        if root_id in _SKIP_ROOTS:
            continue

        label_el = concept.find(f"{{{SKOS}}}prefLabel")
        name = label_el.text.lower().strip() if label_el is not None else cid

        concept_type = _infer_type(name)
        if concept_type == "unknown":
            concept_type = _ACM_ROOT_TYPE.get(root_id, "unknown")

        broader_el = concept.find(f"{{{SKOS}}}broader")
        parent_id  = broader_el.get(f"{{{RDF}}}resource", "").strip() \
                     if broader_el is not None else None

        nodes.append({"id": cid, "name": name,
                      "concept_type": concept_type, "parent_id": parent_id})

        if parent_id and parent_id.count(".") >= 1:
            edges.append((parent_id, cid))

    print(f"[parse-acm] {len(nodes)} concepts, {len(edges)} edges parsed.")
    return nodes, edges


def _insert_acm_nodes_and_edges(
    session:   Session,
    raw_nodes: list[dict],
    raw_edges: list[tuple[str, str]],
) -> None:
    existing: dict[str, int] = {
        sid: dbid
        for sid, dbid in session.query(
            KnowledgeNode.source_id, KnowledgeNode.id
        ).filter(KnowledgeNode.source == "acm_ccs").all()
    }
    acm_id_to_db_id: dict[str, int] = dict(existing)
    inserted_nodes = 0

    for raw in raw_nodes:
        if raw["id"] in existing:
            continue
        node = KnowledgeNode(
            name=raw["name"], description=None, aliases=[],
            concept_type=raw["concept_type"],
            source="acm_ccs", source_id=raw["id"],
        )
        session.add(node)
        session.flush()
        acm_id_to_db_id[raw["id"]] = node.id
        inserted_nodes += 1

    session.commit()
    print(f"[db-acm] Nodes: {inserted_nodes} inserted, "
          f"{len(raw_nodes)-inserted_nodes} already existed.")

    existing_edges: set[tuple[int, int]] = {
        (f, t) for f, t in session.query(
            KnowledgeEdge.from_node_id, KnowledgeEdge.to_node_id).all()
    }
    inserted_edges = 0
    skipped_edges  = 0
    for parent_acm_id, child_acm_id in raw_edges:
        from_id = acm_id_to_db_id.get(parent_acm_id)
        to_id   = acm_id_to_db_id.get(child_acm_id)
        if not from_id or not to_id or from_id == to_id:
            skipped_edges += 1; continue
        if (from_id, to_id) in existing_edges:
            skipped_edges += 1; continue
        session.add(KnowledgeEdge(from_node_id=from_id, to_node_id=to_id,
                                   source="acm_ccs"))
        existing_edges.add((from_id, to_id))
        inserted_edges += 1

    session.commit()
    print(f"[db-acm] Edges: {inserted_edges} inserted, "
          f"{skipped_edges} skipped.")


# ---------------------------------------------------------------------------
# Download + parse metacademy
# ---------------------------------------------------------------------------

def _get_zip_bytes() -> bytes:
    if METACADEMY_ZIP:
        p = Path(METACADEMY_ZIP)
        if not p.exists():
            print(f"ERROR: METACADEMY_ZIP not found: {p}", file=sys.stderr)
            sys.exit(1)
        print(f"[data] Using local archive: {p}")
        return p.read_bytes()

    print("[data] Downloading metacademy-content from GitHub ...")
    try:
        resp = requests.get(_CONTENT_URL, timeout=180, stream=True)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"ERROR: Download failed: {exc}", file=sys.stderr)
        sys.exit(1)

    chunks: list[bytes] = []
    total = 0
    for chunk in resp.iter_content(chunk_size=65_536):
        chunks.append(chunk)
        total += len(chunk)
        print(f"\r  {total/1_048_576:.1f} MB downloaded", end="", flush=True)
    print()
    return b"".join(chunks)


def _read_zip_file(zf: zipfile.ZipFile, path: str) -> str:
    try:
        return zf.read(path).decode("utf-8", errors="replace").strip()
    except KeyError:
        return ""


def _parse_deps_txt(raw: str) -> list[str]:
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
    return re.findall(r'"[^"]+":([a-zA-Z0-9_\-]+)', raw)


def parse_metacademy(zip_bytes: bytes) -> tuple[list[dict], list[tuple[str, str]]]:
    nodes: list[dict]            = []
    edges: list[tuple[str, str]] = []

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        all_names = zf.namelist()
        concept_dirs: set[str] = set()
        for name in all_names:
            m = re.match(r"([^/]+/concepts/)([^/]+)/", name)
            if m:
                concept_dirs.add(m.group(1) + m.group(2) + "/")

        print(f"[parse] Found {len(concept_dirs)} concept directories.")

        for concept_dir in sorted(concept_dirs):
            tag         = concept_dir.rstrip("/").split("/")[-1]
            name        = _read_zip_file(zf, concept_dir + "title.txt")
            description = _read_zip_file(zf, concept_dir + "summary.txt")
            deps_raw    = _read_zip_file(zf, concept_dir + "dependencies.txt")
            see_raw     = _read_zip_file(zf, concept_dir + "see-also.txt")

            if not name:
                name = tag.replace("_", " ").replace("-", " ")

            see_also_tags = _parse_see_also_txt(see_raw)
            aliases = [t.replace("_", " ").replace("-", " ").lower()
                       for t in see_also_tags[:4]]

            nodes.append({
                "tag":         tag,
                "name":        name.lower().strip(),
                "description": description[:1000] if description else None,
                "aliases":     aliases,
            })
            for prereq_tag in _parse_deps_txt(deps_raw):
                edges.append((prereq_tag, tag))

    print(f"[parse] {len(nodes)} nodes, {len(edges)} raw dependency edges.")
    return nodes, edges


# ---------------------------------------------------------------------------
# DB insertion
# ---------------------------------------------------------------------------

def build_graph() -> None:
    zip_bytes = _get_zip_bytes()

    print("\n=== Parsing archive ===")
    raw_nodes, raw_edges = parse_metacademy(zip_bytes)

    if not raw_nodes:
        print("ERROR: No concept nodes found.", file=sys.stderr)
        sys.exit(1)

    engine = create_engine(CONCEPT_DB_URL)

    print("\n=== Writing nodes ===")
    with Session(engine) as session:
        existing: dict[str, int] = {
            sid: dbid for sid, dbid in session.query(
                KnowledgeNode.source_id, KnowledgeNode.id
            ).filter(KnowledgeNode.source == "metacademy").all()
        }
        tag_to_db_id: dict[str, int] = dict(existing)
        inserted_nodes = 0

        for raw in raw_nodes:
            if raw["tag"] in existing:
                continue
            concept_type = _infer_type(raw["name"], raw["description"] or "")
            node = KnowledgeNode(
                name=raw["name"], description=raw["description"],
                aliases=raw["aliases"], concept_type=concept_type,
                source="metacademy", source_id=raw["tag"],
            )
            session.add(node)
            session.flush()
            tag_to_db_id[raw["tag"]] = node.id
            inserted_nodes += 1

        session.commit()
        print(f"[db] Nodes: {inserted_nodes} inserted, "
              f"{len(raw_nodes)-inserted_nodes} already existed.")

        print("\n=== Writing edges ===")
        existing_edges: set[tuple[int, int]] = {
            (f, t) for f, t in session.query(
                KnowledgeEdge.from_node_id, KnowledgeEdge.to_node_id).all()
        }
        inserted_edges = 0
        skipped_edges  = 0

        for prereq_tag, dependent_tag in raw_edges:
            from_id = tag_to_db_id.get(prereq_tag)
            to_id   = tag_to_db_id.get(dependent_tag)
            if not from_id or not to_id or from_id == to_id:
                skipped_edges += 1; continue
            if (from_id, to_id) in existing_edges:
                skipped_edges += 1; continue
            session.add(KnowledgeEdge(from_node_id=from_id, to_node_id=to_id,
                                       source="metacademy"))
            existing_edges.add((from_id, to_id))
            inserted_edges += 1

        session.commit()
        print(f"[db] Edges: {inserted_edges} inserted, "
              f"{skipped_edges} skipped.")

    # ACM CCS
    if ACM_CCS_PATH:
        p = Path(ACM_CCS_PATH)
        if not p.is_absolute():
            p = (Path(__file__).parent / p).resolve()
        if not p.exists():
            print(f"ERROR: ACM_CCS_PATH not found: {p}", file=sys.stderr)
            sys.exit(1)
        print(f"\n=== ACM CCS 2012: {p.name} ===")
        acm_nodes, acm_edges = parse_acm_ccs(str(p))
        with Session(engine) as session:
            _insert_acm_nodes_and_edges(session, acm_nodes, acm_edges)
    else:
        print("\n[acm-ccs] Skipped — set ACM_CCS_PATH in .env to include.")

    # Summary
    with Session(engine) as session:
        total_nodes = session.query(KnowledgeNode).count()
        total_edges = session.query(KnowledgeEdge).count()
        type_rows = (
            session.query(KnowledgeNode.concept_type,
                          func.count(KnowledgeNode.id))
            .group_by(KnowledgeNode.concept_type)
            .order_by(func.count(KnowledgeNode.id).desc())
            .all()
        )

    print(f"\n{'='*60}")
    print(f"  Graph totals: {total_nodes} nodes, {total_edges} edges")
    print(f"{'='*60}")
    for ctype, count in type_rows:
        print(f"  {ctype:<26} {count}")


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"  Knowledge Graph Builder")
    print(f"  Sources: Metacademy")
    if ACM_CCS_PATH:
        print(f"           ACM CCS 2012  ({ACM_CCS_PATH})")
    else:
        print(f"           ACM CCS 2012  (skipped — set ACM_CCS_PATH in .env)")
    print(f"{'='*60}\n")
    build_graph()