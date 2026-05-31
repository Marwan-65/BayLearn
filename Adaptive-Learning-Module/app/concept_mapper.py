"""
concept_mapper.py
=================
Maps extracted concepts (from the `concepts` table) to canonical nodes in
the knowledge graph (`knowledge_nodes`) using a three-stage pipeline:

  Stage 1 — Exact lookup
      Normalised name and alias string matching against all node names/aliases.
      Zero model cost, perfect precision.

  Stage 2 — Type-scoped bi-encoder retrieval
      The extracted concept is embedded with a sentence-transformer bi-encoder.
      A FAISS index is queried — same-type nodes first (type-scoped), then
      the global index as a fallback — to retrieve the top-K candidates.
      Type-scoping dramatically reduces false positives (e.g. "heap" the
      data structure vs "heap" the memory region).

  Stage 3 — Cross-encoder reranking
      The (concept text, candidate text) pair is scored by a cross-encoder.
      Unlike the bi-encoder which embeds both sides independently, the
      cross-encoder attends across both strings simultaneously, catching
      semantic nuances that cosine similarity misses.
      The best candidate above MATCH_THRESHOLD is stored as the mapping.

Results are written to `concept_node_mappings`.
Concepts with no match above the threshold are left unmapped (novel nodes
that don't exist in the current knowledge graph).

Usage:
    python concept_mapper.py --course-name "Operating Systems"
    python concept_mapper.py --course-id 3
    python concept_mapper.py               # maps every course

Models are downloaded automatically from HuggingFace on first run:
    Bi-encoder   : sentence-transformers/all-mpnet-base-v2  (~420 MB)
    Cross-encoder: cross-encoder/ms-marco-MiniLM-L-6-v2    (~60 MB)

Node embeddings are cached in CACHE_DIR so they are only computed once.
The cache is automatically invalidated when the knowledge_nodes row count
changes (i.e. after running build_knowledge_graph.py again).

Required .env key:
    CONCEPT_DB_URL

Optional .env keys:
    BI_ENCODER_MODEL    (default: sentence-transformers/all-mpnet-base-v2)
    CROSS_ENCODER_MODEL (default: cross-encoder/ms-marco-MiniLM-L-6-v2)
    TOP_K               (default: 10)   bi-encoder candidates per concept
    MATCH_THRESHOLD     (default: 0.50) min cross-encoder sigmoid score
    CACHE_DIR           (default: ./cache)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

import numpy as np
from dotenv import load_dotenv
from sqlalchemy import Column, Float, ForeignKey, Integer, JSON, String, Text, create_engine
from sqlalchemy.orm import declarative_base, Session

load_dotenv(Path(__file__).parent / ".env")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONCEPT_DB_URL      = os.environ.get("CONCEPT_DB_URL", "").strip()
BI_ENCODER_MODEL    = os.environ.get("BI_ENCODER_MODEL",
                                     "sentence-transformers/all-mpnet-base-v2").strip()
CROSS_ENCODER_MODEL = os.environ.get("CROSS_ENCODER_MODEL",
                                     "cross-encoder/ms-marco-MiniLM-L-6-v2").strip()
TOP_K               = int(os.environ.get("TOP_K", "10"))
MATCH_THRESHOLD     = float(os.environ.get("MATCH_THRESHOLD", "0.50"))
CACHE_DIR           = Path(os.environ.get("CACHE_DIR", "./cache"))

if not CONCEPT_DB_URL:
    print("ERROR: CONCEPT_DB_URL not set in .env", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# SQLAlchemy models  (read: courses, concepts / write: concept_node_mappings)
# ---------------------------------------------------------------------------

Base = declarative_base()


class Course(Base):
    __tablename__ = "courses"
    id   = Column(Integer, primary_key=True)
    name = Column(String,  nullable=False)


class Concept(Base):
    __tablename__ = "concepts"
    id           = Column(Integer, primary_key=True)
    course_id    = Column(Integer, ForeignKey("courses.id"), nullable=False)
    name         = Column(String,  nullable=False)
    difficulty   = Column(Integer, nullable=False)
    aliases      = Column(JSON,    nullable=False, default=list)
    concept_type = Column(String,  nullable=False, default="unknown")


class KnowledgeNode(Base):
    __tablename__ = "knowledge_nodes"
    id           = Column(Integer, primary_key=True)
    name         = Column(String,  nullable=False)
    description  = Column(Text)
    aliases      = Column(JSON,    nullable=False, default=list)
    concept_type = Column(String,  nullable=False, default="unknown")
    source       = Column(String,  nullable=False)
    source_id    = Column(String)


class ConceptNodeMapping(Base):
    __tablename__ = "concept_node_mappings"
    concept_id  = Column(Integer, ForeignKey("concepts.id",        ondelete="CASCADE"), primary_key=True)
    node_id     = Column(Integer, ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), primary_key=True)
    confidence  = Column(Float,   nullable=False)
    match_type  = Column(String,  nullable=False)   # exact_name | exact_alias | semantic


# ---------------------------------------------------------------------------
# Text representations
# Enriched text gives the embedding model more signal to work with.
# ---------------------------------------------------------------------------

def _node_to_doc(node: KnowledgeNode) -> str:
    """
    Build the embedding document for a knowledge graph node.
    Format: "{name}. {aliases}. {description}. ({type})"
    """
    parts: list[str] = [node.name]
    aliases = node.aliases or []
    if aliases:
        parts.append(", ".join(str(a) for a in aliases[:4]))
    if node.description:
        parts.append(node.description[:400])
    ctype = (node.concept_type or "unknown").replace("_", " ")
    if ctype != "unknown":
        parts.append(f"({ctype})")
    return ". ".join(parts)


def _concept_to_query(concept: Concept) -> str:
    """
    Build the query text for an extracted concept.
    Includes name, aliases, and type label to help the bi-encoder.
    """
    parts: list[str] = [concept.name]
    aliases = concept.aliases or []
    if aliases:
        parts.append(", ".join(str(a) for a in aliases[:3]))
    ctype = (concept.concept_type or "unknown").replace("_", " ")
    if ctype != "unknown":
        parts.append(f"({ctype})")
    return ". ".join(parts)


# ---------------------------------------------------------------------------
# Normalisation helper (shared with build_knowledge_graph.py logic)
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    return " ".join(s.lower().split())


# ---------------------------------------------------------------------------
# Embedding cache
# Embeddings for knowledge_nodes are stored as two .npy files:
#   {cache_dir}/node_ids.npy          — int32 array of knowledge_node.id
#   {cache_dir}/node_embeddings.npy   — float32 (N, dim) array
# A {cache_dir}/meta.json records the row count at cache-build time so we
# can detect when build_knowledge_graph.py has added new nodes.
# ---------------------------------------------------------------------------

def _cache_paths() -> tuple[Path, Path, Path]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return (
        CACHE_DIR / "node_ids.npy",
        CACHE_DIR / "node_embeddings.npy",
        CACHE_DIR / "meta.json",
    )


def _cache_valid(node_count: int) -> bool:
    ids_path, emb_path, meta_path = _cache_paths()
    if not (ids_path.exists() and emb_path.exists() and meta_path.exists()):
        return False
    try:
        meta = json.loads(meta_path.read_text())
        return meta.get("node_count") == node_count
    except Exception:
        return False


def _save_cache(ids: np.ndarray, embeddings: np.ndarray, node_count: int) -> None:
    ids_path, emb_path, meta_path = _cache_paths()
    np.save(str(ids_path), ids)
    np.save(str(emb_path), embeddings)
    meta_path.write_text(json.dumps({"node_count": node_count}))


def _load_cache() -> tuple[np.ndarray, np.ndarray]:
    ids_path, emb_path, _ = _cache_paths()
    return np.load(str(ids_path)), np.load(str(emb_path))


# ---------------------------------------------------------------------------
# FAISS index builder
# We use IndexFlatIP (inner product) with L2-normalised vectors, which is
# equivalent to cosine similarity. One index per concept_type + one global.
# ---------------------------------------------------------------------------

def _build_indices(
    node_ids:   np.ndarray,   # int32 (N,)
    embeddings: np.ndarray,   # float32 (N, dim) — already L2-normalised
    nodes_by_id: dict[int, KnowledgeNode],
) -> tuple[dict[str, tuple], tuple]:
    """
    Returns:
      type_indices  : { concept_type -> (faiss_index, id_array) }
      global_index  : (faiss_index, id_array)
    """
    import faiss  # imported here so the rest of the file loads without faiss

    dim = embeddings.shape[1]

    # ── Global index ──────────────────────────────────────────────────────
    global_idx   = faiss.IndexFlatIP(dim)
    global_idx.add(embeddings)
    global_tuple = (global_idx, node_ids)

    # ── Per-type indices ──────────────────────────────────────────────────
    type_indices: dict[str, tuple] = {}
    # Group node positions by type
    type_to_positions: dict[str, list[int]] = {}
    for pos, nid in enumerate(node_ids):
        ctype = nodes_by_id[int(nid)].concept_type or "unknown"
        type_to_positions.setdefault(ctype, []).append(pos)

    for ctype, positions in type_to_positions.items():
        if len(positions) == 0:
            continue
        pos_arr  = np.array(positions, dtype=np.int64)
        type_emb = embeddings[pos_arr]   # subset
        type_ids = node_ids[pos_arr]
        idx      = faiss.IndexFlatIP(dim)
        idx.add(type_emb)
        type_indices[ctype] = (idx, type_ids)

    return type_indices, global_tuple


# ---------------------------------------------------------------------------
# Exact-match lookup table
# ---------------------------------------------------------------------------

def _build_alias_lookup(nodes: list[KnowledgeNode]) -> dict[str, KnowledgeNode]:
    lookup: dict[str, KnowledgeNode] = {}
    for node in nodes:
        lookup[_norm(node.name)] = node
        for alias in (node.aliases or []):
            key = _norm(str(alias))
            if key and key not in lookup:
                lookup[key] = node
    return lookup


# ---------------------------------------------------------------------------
# Core mapping logic
# ---------------------------------------------------------------------------

def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + np.exp(-x))


def map_concepts_for_course(
    course_id:     int,
    session:       Session,
    bi_encoder,
    cross_encoder,
    nodes:         list[KnowledgeNode],
    nodes_by_id:   dict[int, KnowledgeNode],
    alias_lookup:  dict[str, KnowledgeNode],
    type_indices:  dict[str, tuple],
    global_index:  tuple,
) -> tuple[dict[str, int], list[dict]]:
    """
    Map every concept in the given course to a knowledge node (if found).

    Returns:
        summary : {match_type: count}
        details : one record per concept, containing:
            - concept_name, concept_type
            - match_type  ("exact_name" | "exact_alias" | "semantic" | "no_match")
            - node_name, node_type, node_source, node_id  (None if no match)
            - confidence                                  (None if no match)
            - best_miss_name, best_miss_score             (set when no_match,
              showing what came closest so threshold issues are visible)
    """
    concepts: list[Concept] = (
        session.query(Concept)
        .filter(Concept.course_id == course_id)
        .all()
    )
    if not concepts:
        print(f"  [map] No concepts found for course_id={course_id}.")
        return {}, []

    # Load already-mapped concept ids to skip them
    already_mapped: set[int] = {
        row.concept_id
        for row in session.query(ConceptNodeMapping.concept_id)
                          .filter(
                              ConceptNodeMapping.concept_id.in_(
                                  [c.id for c in concepts]
                              )
                          )
                          .all()
    }

    to_map = [c for c in concepts if c.id not in already_mapped]
    print(f"  [map] {len(concepts)} concepts total, "
          f"{len(to_map)} need mapping, {len(already_mapped)} already mapped.")

    if not to_map:
        return {"already_mapped": len(already_mapped)}, []

    summary: dict[str, int] = {"exact_name": 0, "exact_alias": 0, "semantic": 0, "no_match": 0}
    details: list[dict]     = []
    new_mappings: list[ConceptNodeMapping] = []

    for concept in to_map:
        norm_name = _norm(concept.name)

        # ── Stage 1a: exact name match ────────────────────────────────────
        if norm_name in alias_lookup:
            node = alias_lookup[norm_name]
            new_mappings.append(ConceptNodeMapping(
                concept_id = concept.id,
                node_id    = node.id,
                confidence = 1.0,
                match_type = "exact_name",
            ))
            summary["exact_name"] += 1
            details.append(_match_record(concept, node, "exact_name", 1.0))
            continue

        # ── Stage 1b: exact alias match ───────────────────────────────────
        exact_node: Optional[KnowledgeNode] = None
        for alias in (concept.aliases or []):
            key = _norm(str(alias))
            if key in alias_lookup:
                exact_node = alias_lookup[key]
                break
        if exact_node is not None:
            new_mappings.append(ConceptNodeMapping(
                concept_id = concept.id,
                node_id    = exact_node.id,
                confidence = 1.0,
                match_type = "exact_alias",
            ))
            summary["exact_alias"] += 1
            details.append(_match_record(concept, exact_node, "exact_alias", 1.0))
            continue

        # ── Stage 2: bi-encoder candidate retrieval ───────────────────────
        query_text = _concept_to_query(concept)
        query_vec  = bi_encoder.encode(
            query_text,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).astype(np.float32).reshape(1, -1)

        candidates: list[tuple[KnowledgeNode, float]] = []
        seen_ids:   set[int] = set()

        # Type-scoped search first
        ctype = concept.concept_type or "unknown"
        if ctype in type_indices:
            typed_idx, typed_ids = type_indices[ctype]
            k = min(TOP_K, typed_idx.ntotal)
            if k > 0:
                D, I = typed_idx.search(query_vec, k)
                for dist, pos in zip(D[0], I[0]):
                    if pos >= 0:
                        nid  = int(typed_ids[pos])
                        node = nodes_by_id.get(nid)
                        if node and nid not in seen_ids:
                            candidates.append((node, float(dist)))
                            seen_ids.add(nid)

        # Global index top-up (catches cross-type matches)
        global_idx, global_ids = global_index
        k_global = min(TOP_K, global_idx.ntotal)
        if k_global > 0:
            D, I = global_idx.search(query_vec, k_global)
            for dist, pos in zip(D[0], I[0]):
                if pos >= 0:
                    nid  = int(global_ids[pos])
                    node = nodes_by_id.get(nid)
                    if node and nid not in seen_ids:
                        candidates.append((node, float(dist)))
                        seen_ids.add(nid)

        if not candidates:
            summary["no_match"] += 1
            details.append(_miss_record(concept, None, None))
            continue

        # ── Stage 3: cross-encoder reranking ─────────────────────────────
        pairs: list[tuple[str, str]] = [
            (query_text, _node_to_doc(c[0]))
            for c in candidates
        ]
        raw_scores: np.ndarray = cross_encoder.predict(
            pairs,
            show_progress_bar=False,
        )
        # Apply sigmoid to convert logits → [0, 1]
        scores = np.array([_sigmoid(float(s)) for s in raw_scores])

        best_pos   = int(np.argmax(scores))
        best_score = float(scores[best_pos])
        best_node  = candidates[best_pos][0]

        if best_score < MATCH_THRESHOLD:
            summary["no_match"] += 1
            details.append(_miss_record(concept, best_node, best_score))
            continue

        new_mappings.append(ConceptNodeMapping(
            concept_id = concept.id,
            node_id    = best_node.id,
            confidence = round(best_score, 4),
            match_type = "semantic",
        ))
        summary["semantic"] += 1
        details.append(_match_record(concept, best_node, "semantic",
                                     round(best_score, 4)))

    # ── Bulk insert mappings ──────────────────────────────────────────────
    for mapping in new_mappings:
        session.add(mapping)
    session.commit()

    return summary, details


# ---------------------------------------------------------------------------
# Detail record helpers
# ---------------------------------------------------------------------------

def _match_record(
    concept:    Concept,
    node:       KnowledgeNode,
    match_type: str,
    confidence: float,
) -> dict:
    return {
        "concept_name": concept.name,
        "concept_type": concept.concept_type or "unknown",
        "match_type":   match_type,
        "node_id":      node.id,
        "node_name":    node.name,
        "node_type":    node.concept_type or "unknown",
        "node_source":  node.source,
        "confidence":   confidence,
        "best_miss_name":  None,
        "best_miss_score": None,
    }


def _miss_record(
    concept:    Concept,
    best_node:  Optional[KnowledgeNode],
    best_score: Optional[float],
) -> dict:
    return {
        "concept_name": concept.name,
        "concept_type": concept.concept_type or "unknown",
        "match_type":   "no_match",
        "node_id":      None,
        "node_name":    None,
        "node_type":    None,
        "node_source":  None,
        "confidence":   None,
        "best_miss_name":  best_node.name if best_node else None,
        "best_miss_score": round(best_score, 4) if best_score is not None else None,
    }


def show_existing_mappings(
    courses:     list[Course],
    session:     Session,
    nodes_by_id: dict[int, KnowledgeNode],
) -> None:
    """
    Print all existing concept_node_mappings for the given courses.
    No model loading required — reads directly from the DB.
    """
    for course in courses:
        concepts: list[Concept] = (
            session.query(Concept)
            .filter(Concept.course_id == course.id)
            .all()
        )
        concept_by_id = {c.id: c for c in concepts}

        mappings = (
            session.query(ConceptNodeMapping)
            .filter(ConceptNodeMapping.concept_id.in_(list(concept_by_id.keys())))
            .all()
        )

        unmapped = [
            c for c in concepts
            if c.id not in {m.concept_id for m in mappings}
        ]

        print(f"=== Course [{course.id}] '{course.name}' "
              f"— {len(mappings)} mapped, {len(unmapped)} unmapped ===")

        if mappings:
            print(f"\n  MAPPED ({len(mappings)}):")
            print(f"  {'─'*70}")
            for m in sorted(mappings,
                            key=lambda x: concept_by_id[x.concept_id].name):
                concept = concept_by_id[m.concept_id]
                node    = nodes_by_id.get(m.node_id)
                tag = {
                    "exact_name":  "exact ",
                    "exact_alias": "alias ",
                    "semantic":    f"  {m.confidence:.2f}",
                }.get(m.match_type, "      ")
                node_name   = node.name   if node else f"[node_id={m.node_id}]"
                node_source = node.source if node else "?"
                print(
                    f"  ✓ [{tag}]  "
                    f"{concept.name:<32}  "
                    f"→  {node_name:<32}  "
                    f"[{node_source:<10}]"
                )

        if unmapped:
            print(f"\n  UNMAPPED ({len(unmapped)}):")
            print(f"  {'─'*70}")
            for c in sorted(unmapped, key=lambda x: x.name):
                print(f"  ✗ {c.name:<38}  [{c.concept_type}]")

        print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(args: argparse.Namespace) -> None:
    print(f"\n{'='*60}")
    print(f"  Concept Mapper")
    if not args.show_mapped:
        print(f"  Bi-encoder   : {BI_ENCODER_MODEL}")
        print(f"  Cross-encoder: {CROSS_ENCODER_MODEL}")
        print(f"  Top-K        : {TOP_K}")
        print(f"  Threshold    : {MATCH_THRESHOLD}")
        print(f"  Cache dir    : {CACHE_DIR}")
    else:
        print(f"  Mode         : show existing mappings (no model loading)")
    print(f"{'='*60}\n")

    engine = create_engine(CONCEPT_DB_URL)

    with Session(engine) as session:
        # ── Resolve which courses to process ──────────────────────────────
        if args.course_id:
            courses: list[Course] = [session.get(Course, args.course_id)]
            if courses[0] is None:
                print(f"ERROR: course_id={args.course_id} not found.", file=sys.stderr)
                sys.exit(1)
        elif args.course_name:
            course = (
                session.query(Course)
                .filter(Course.name == args.course_name)
                .first()
            )
            if course is None:
                print(f"ERROR: course '{args.course_name}' not found.", file=sys.stderr)
                sys.exit(1)
            courses = [course]
        else:
            courses = session.query(Course).all()

        print(f"[courses] Processing {len(courses)} course(s):")
        for c in courses:
            print(f"  • [{c.id}] {c.name}")

        # ── --show-mapped: read-only display, no models needed ─────────────
        if args.show_mapped:
            print("\n[graph] Loading knowledge nodes for display …")
            nodes: list[KnowledgeNode] = session.query(KnowledgeNode).all()
            nodes_by_id = {n.id: n for n in nodes}
            print()
            show_existing_mappings(courses, session, nodes_by_id)
            return

        # ── Load knowledge nodes for mapping ──────────────────────────────
        print("\n[graph] Loading knowledge nodes …")
        nodes: list[KnowledgeNode] = session.query(KnowledgeNode).all()
        session.expunge_all()

    if not nodes:
        print("ERROR: knowledge_nodes table is empty. Run build_knowledge_graph.py first.",
              file=sys.stderr)
        sys.exit(1)

    node_count   = len(nodes)
    nodes_by_id  = {n.id: n for n in nodes}
    alias_lookup = _build_alias_lookup(nodes)
    print(f"[graph] {node_count} nodes loaded, {len(alias_lookup)} alias lookup entries.")

    # ── Load / build embedding cache ─────────────────────────────────────
    print("\n[embed] Loading bi-encoder model …")
    from sentence_transformers import SentenceTransformer  # deferred import
    bi_encoder = SentenceTransformer(BI_ENCODER_MODEL)

    if _cache_valid(node_count):
        print("[embed] Cache hit — loading node embeddings from disk.")
        node_ids_arr, node_emb_arr = _load_cache()
    else:
        print(f"[embed] Cache miss — embedding {node_count} nodes (this runs once) …")
        docs = [_node_to_doc(n) for n in nodes]
        node_emb_arr = bi_encoder.encode(
            docs,
            normalize_embeddings=True,
            batch_size=64,
            show_progress_bar=True,
        ).astype(np.float32)
        node_ids_arr = np.array([n.id for n in nodes], dtype=np.int32)
        _save_cache(node_ids_arr, node_emb_arr, node_count)
        print(f"[embed] Embeddings cached to {CACHE_DIR}/")

    # ── Build FAISS indices ───────────────────────────────────────────────
    print("[index] Building FAISS indices …")
    type_indices, global_index = _build_indices(node_ids_arr, node_emb_arr, nodes_by_id)
    type_summary = {k: v[1].shape[0] for k, v in type_indices.items()}
    print(f"[index] Global index: {global_index[0].ntotal} vectors")
    print(f"[index] Type-scoped indices:")
    for ctype, count in sorted(type_summary.items(), key=lambda x: -x[1]):
        print(f"         {ctype:<26} {count}")

    # ── Load cross-encoder ────────────────────────────────────────────────
    print("\n[rerank] Loading cross-encoder model …")
    from sentence_transformers.cross_encoder import CrossEncoder  # deferred import
    cross_encoder = CrossEncoder(CROSS_ENCODER_MODEL)

    # ── Map each course ───────────────────────────────────────────────────
    print()
    with Session(engine) as session:
        for course in courses:
            print(f"=== Mapping course [{course.id}] '{course.name}' ===")
            summary, details = map_concepts_for_course(
                course_id     = course.id,
                session       = session,
                bi_encoder    = bi_encoder,
                cross_encoder = cross_encoder,
                nodes         = nodes,
                nodes_by_id   = nodes_by_id,
                alias_lookup  = alias_lookup,
                type_indices  = type_indices,
                global_index  = global_index,
            )

            _print_mapping_details(details)

            print(f"  [result] exact_name={summary.get('exact_name', 0)}  "
                  f"exact_alias={summary.get('exact_alias', 0)}  "
                  f"semantic={summary.get('semantic', 0)}  "
                  f"no_match={summary.get('no_match', 0)}")
            print()

    print("[done] Mapping complete.")


def _print_mapping_details(details: list[dict]) -> None:
    """Print a formatted breakdown of matched and unmatched concepts."""
    if not details:
        return

    matched  = [d for d in details if d["match_type"] != "no_match"]
    unmatched = [d for d in details if d["match_type"] == "no_match"]

    # ── Matched ───────────────────────────────────────────────────────────
    if matched:
        print(f"\n  MATCHED ({len(matched)}):")
        print(f"  {'─'*70}")
        for d in matched:
            tag = {
                "exact_name":  "exact ",
                "exact_alias": "alias ",
                "semantic":    f"  {d['confidence']:.2f}",
            }.get(d["match_type"], "      ")

            src_badge = f"[{d['node_source']:<10}]" if d["node_source"] else ""
            print(
                f"  ✓ [{tag}]  "
                f"{d['concept_name']:<32}  "
                f"→  {d['node_name']:<32}  "
                f"{src_badge}"
            )

    # ── Unmatched ─────────────────────────────────────────────────────────
    if unmatched:
        print(f"\n  NO MATCH ({len(unmatched)}):")
        print(f"  {'─'*70}")
        for d in unmatched:
            miss_hint = ""
            if d["best_miss_name"] is not None:
                miss_hint = (
                    f"  (best: '{d['best_miss_name']}' "
                    f"score={d['best_miss_score']:.2f})"
                )
            print(f"  ✗ {d['concept_name']:<38}  [{d['concept_type']}]{miss_hint}")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Map extracted concepts to knowledge graph nodes."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--course-id",   type=int,  help="Target a single course by DB id")
    group.add_argument("--course-name", type=str,  help="Target a single course by name")
    parser.add_argument(
        "--show-mapped",
        action="store_true",
        help="Print existing mappings for the course(s) without running the models.",
    )
    main(parser.parse_args())