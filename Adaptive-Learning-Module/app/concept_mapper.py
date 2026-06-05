
# da by run ba3d el build_knowledge_graph.py fa el data btkoon already mawgooda
#el file hadafo eno y-match el concepts bl knowledge nodes w bye3mel kda 3la 3 stages
# awel stage howa el exact lookup by normalising el names w el aliases w by3mel match 3lehom
# el stage el tany howa el bi-encoder retrieval by building FAISS index 3la el node embeddings w by3mel search 3lehom by type aw global. Type-scoping reduces false positives (e.g. "heap" data structure vs "heap" memory region).
# el stage el talet howa el cross-encoder reranking by scoring pairs of (concept text, candidate node text) w by5od el best candidate law el score bta3o akbar men el threshold
'''
Optional .env keys:
    BI_ENCODER_MODEL    (default: sentence-transformers/all-mpnet-base-v2)
    CROSS_ENCODER_MODEL (default: cross-encoder/nli-deberta-v3-small)
    TOP_K               (default: 15)
    MATCH_THRESHOLD     (default: 0.80)
    CACHE_DIR           (default: ./cache)
'''
# el run command: python concept_mapper.py --course-name "Operating Systems" awlw mn 8er flag hayeshta8al 3la kol el courses el mawgooda

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

#configure el environment variables w el defaults
CONCEPT_DB_URL = os.environ.get("CONCEPT_DB_URL", "").strip()
BI_ENCODER_MODEL = os.environ.get("BI_ENCODER_MODEL", "sentence-transformers/all-mpnet-base-v2")
CROSS_ENCODER_MODEL = os.environ.get("CROSS_ENCODER_MODEL", "cross-encoder/nli-deberta-v3-small")
TOP_K = int(os.environ.get("TOP_K",  "15"))
MATCH_THRESHOLD = float(os.environ.get("MATCH_THRESHOLD", "0.80"))
CACHE_DIR = Path(os.environ.get("CACHE_DIR","./cache"))

if not CONCEPT_DB_URL:
    print("ERROR: CONCEPT_DB_URL not set in .env", file=sys.stderr)
    sys.exit(1)


# dol el orm models, el cocnepts.id string 3ashan UUID, w knowledge_nodes.id integer 3ashan howa auto-increment
Base = declarative_base()


class Course(Base):
    __tablename__ = "courses"
    id   = Column(String,  primary_key=True)   #varchar uuid
    name = Column(String,  nullable=False)


class Concept(Base):
    __tablename__ = "concepts"
    id           = Column(String,  primary_key=True)   # VARCHAR UUID
    course_id    = Column(String,  ForeignKey("courses.id"), nullable=False)
    name         = Column(String,  nullable=False)
    difficulty   = Column(Integer, nullable=False)
    aliases      = Column(JSON,    nullable=False, default=list)
    concept_type = Column(String,  nullable=False, default="unknown")


class KnowledgeNode(Base):
    __tablename__ = "knowledge_nodes"
    id           = Column(Integer, primary_key=True, autoincrement=True)
    name         = Column(String,  nullable=False)
    description  = Column(Text)
    aliases      = Column(JSON,    nullable=False, default=list)
    concept_type = Column(String,  nullable=False, default="unknown")
    source       = Column(String,  nullable=False)
    source_id    = Column(String)

# 5aly balak mn types el ID
class ConceptNodeMapping(Base):
    __tablename__ = "concept_node_mappings"
    # concept_id : VARCHAR UUID  (concepts.id)
    # node_id : INTEGER (knowledge_nodes.id)
    concept_id  = Column(String,  ForeignKey("concepts.id", ondelete="CASCADE"), primary_key=True)
    node_id     = Column(Integer, ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), primary_key=True)
    confidence  = Column(Float,  nullable=False)
    match_type  = Column(String, nullable=False)


# by7awel el KnowledgeNode le string representation by combine el name w up to 4 aliases w el description w el concept type in parenthsis, 3shan lama el bi-encoder yembed el node, yeb2a 3ando aktr ma3loumat yeb2a a7san. El concept kaman byeb2a le string representation zayda shwaya 3shan lama n embed el query text bta3o, yeb2a feh aktr ma3loumat kaman.
def _node_to_doc(node: KnowledgeNode) -> str:
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

# nafs el kalam bs ll concepts badal el node. el ma3lomat el bya5odha heya name, up to 3 aliases, type. mafeesh description 3shan el concepts malhash
def _concept_to_query(concept: Concept) -> str:
    parts: list[str] = [concept.name]
    aliases = concept.aliases or []
    if aliases:
        parts.append(", ".join(str(a) for a in aliases[:3]))
    ctype = (concept.concept_type or "unknown").replace("_", " ")
    if ctype != "unknown":
        parts.append(f"({ctype})")
    return ". ".join(parts)

#normalisation: 5aly kolo lowercase w 5aly el whitespace 3ebara 3n single space 3shan el exact matching yeshta8al
def _norm(s: str) -> str:
    return " ".join(s.lower().split())



#7war el embedding da lama ne3melo thousands of times bya5od wa2t kbeer, fa hane3mel cache 3shan msh kol marra ne3mel el kalam da

#define el paths el gowa el cache
def _cache_paths() -> tuple[Path, Path, Path]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return (
        CACHE_DIR / "node_ids.npy",
        CACHE_DIR / "node_embeddings.npy",
        CACHE_DIR / "meta.json",
    )

#et2aked en el cache momken nesta5demo tany. el 3 files lazem yeb2o mawgodeen, wl node count lazem yeb2a zy 3adda el nodes el fl DB, lw 7aga menhom msh mawgooda hane3mel computation 3la kol el nodes tny
def _cache_valid(node_count: int) -> bool:
    ids_path, emb_path, meta_path = _cache_paths()
    if not (ids_path.exists() and emb_path.exists() and meta_path.exists()):
        return False
    try:
        meta = json.loads(meta_path.read_text())
        return meta.get("node_count") == node_count
    except Exception:
        return False

#save w load el cache. straightforward file io
def _save_cache(ids: np.ndarray, embeddings: np.ndarray,
                node_count: int) -> None:
    ids_path, emb_path, meta_path = _cache_paths()
    np.save(str(ids_path), ids)
    np.save(str(emb_path), embeddings)
    meta_path.write_text(json.dumps({"node_count": node_count}))


def _load_cache() -> tuple[np.ndarray, np.ndarray]:
    ids_path, emb_path, _ = _cache_paths()
    return np.load(str(ids_path)), np.load(str(emb_path))


# ---------------------------------------------------------------------------
# FAISS index
# node_ids are int32 arrays — knowledge_nodes.id is INTEGER
# ---------------------------------------------------------------------------

# hena di responsible 3la build el FAISS indices. hayeb2a 3ndena global index 3la kol el nodes, w type-specific indices 3la kol concept type (e.g. "data structure", "algorithm", "theorem") 3shan nreduce el false positives w n improve el relevance. 
# betakhod el node_ids w el embeddings w el nodes_by_id dict 3shan t3raf el concept type bta3 kol node w te3mel grouping 3lehom 3la asas el concept type. ba3d kda hayeb2a betbuild el FAISS index 3la kol group w te5zen el index w el corresponding node_ids fe dicts w tuples w terga3hom.
def _build_indices(
    node_ids:    np.ndarray,          # int32 (N,)
    embeddings:  np.ndarray,          # float32 (N, dim) L2-normalised
    nodes_by_id: dict[int, KnowledgeNode],
) -> tuple[dict[str, tuple], tuple]:
    import faiss

    dim          = embeddings.shape[1]
    global_idx   = faiss.IndexFlatIP(dim)
    global_idx.add(embeddings)
    global_tuple = (global_idx, node_ids)

    type_to_positions: dict[str, list[int]] = {}
    for pos, nid in enumerate(node_ids): # el node_ids array howa int32, fa lazm nconvert le int normal
        ctype = nodes_by_id[int(nid)].concept_type or "unknown"
        type_to_positions.setdefault(ctype, []).append(pos)

    type_indices: dict[str, tuple] = {} # el key howa el concept type, w el value howa tuple feha el FAISS index w el corresponding node_ids array
    for ctype, positions in type_to_positions.items():
        pos_arr  = np.array(positions, dtype=np.int64)
        type_emb = embeddings[pos_arr]
        type_ids = node_ids[pos_arr]
        idx      = faiss.IndexFlatIP(dim)
        idx.add(type_emb)
        type_indices[ctype] = (idx, type_ids)

    return type_indices, global_tuple


#awel stage, exact lookup, o(1) w mn 8er models wla ay 7aga
def _build_alias_lookup(
    nodes: list[KnowledgeNode],
) -> dict[str, KnowledgeNode]:
    lookup: dict[str, KnowledgeNode] = {}
    for node in nodes:
        lookup[_norm(node.name)] = node
        for alias in (node.aliases or []):
            key = _norm(str(alias))
            if key and key not in lookup:
                lookup[key] = node
    return lookup



# SECTION 7: Core Mapping logic


#standard sigmoid, bta5od logit w bterga3 confidence score ben 0 w 1
def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + np.exp(-x))

# el function el ra2iseya el betakhod course_id w session w el models w el data structures el m7taga 3shan t3mel el mapping. haygeb kol el concepts el mawgodeen lel course, yshof ay concepts lazem yetmapo (i.e. mafeesh mapping mawgood already), w by3mel 3 stages: exact name/alias lookup, bi-encoder retrieval, cross-encoder reranking. 
# by7seb summary stats 3an kol stage w bygeb details 3an kol concept (e.g. best match even law mafeesh match akbar men el threshold) 3shan n3raf n7assan fe eh w n7assan el models w el data. ba3d kda hayinsert el mappings el gedida fe database w yerga3 el summary w details.
def map_concepts_for_course(
    course_id: str,   # VARCHAR UUID
    session:   Session,
    bi_encoder,
    cross_encoder,
    nodes:    list[KnowledgeNode],
    nodes_by_id: dict[int, KnowledgeNode],
    alias_lookup:dict[str, KnowledgeNode],
    type_indices: dict[str, tuple],
    global_index: tuple,
) -> tuple[dict[str, int], list[dict]]:
    concepts: list[Concept] = (
        session.query(Concept)
        .filter(Concept.course_id == course_id)
        .all()
    )
    if not concepts:
        print(f"  [map] No concepts found for course_id={course_id}.")
        return {}, []

    already_mapped: set[str] = {# el already_mapped set howa set feha concept_id (VARCHAR UUID) lel concepts el mawgodeen lel course, w el mapping mawgood already fe database. by3mel query 3la ConceptNodeMapping 3shan ygeb el concept_ids el mawgodeen feha mapping, w by7otohom fe set 3shan lookup o(1) ba3d kda.
        row.concept_id
        for row in session.query(ConceptNodeMapping.concept_id).filter(ConceptNodeMapping.concept_id.in_([c.id for c in concepts]) ).all() } 

    to_map = [c for c in concepts if c.id not in already_mapped]
    print(f"  [map] {len(concepts)} concepts, "
          f"{len(to_map)} need mapping, {len(already_mapped)} already mapped.")

    if not to_map:
        return {"already_mapped": len(already_mapped)}, []

    summary: dict[str, int] = {
        "exact_name": 0, "exact_alias": 0, "semantic": 0, "no_match": 0
    }
    details:      list[dict]               = []
    new_mappings: list[ConceptNodeMapping] = []

    for concept in to_map:
        norm_name = _norm(concept.name)

        # Stage 1a, exact name
        if norm_name in alias_lookup:
            node = alias_lookup[norm_name]
            new_mappings.append(ConceptNodeMapping(
                concept_id=concept.id, node_id=node.id,
                confidence=1.0, match_type="exact_name",
            ))
            summary["exact_name"] += 1
            details.append(_match_record(concept, node, "exact_name", 1.0))
            continue

        # Stage 1b, exact alias
        exact_node: Optional[KnowledgeNode] = None
        for alias in (concept.aliases or []):
            key = _norm(str(alias))
            if key in alias_lookup:
                exact_node = alias_lookup[key]
                break
        if exact_node is not None:
            new_mappings.append(ConceptNodeMapping(
                concept_id=concept.id, node_id=exact_node.id,
                confidence=1.0, match_type="exact_alias",
            ))
            summary["exact_alias"] += 1
            details.append(_match_record(concept, exact_node, "exact_alias", 1.0))
            continue

        # Stage 2, bi-encoder retrieval
        query_text = _concept_to_query(concept)
        query_vec  = bi_encoder.encode(
            query_text, normalize_embeddings=True,
            show_progress_bar=False,
        ).astype(np.float32).reshape(1, -1)

        candidates: list[tuple[KnowledgeNode, float]] = []
        seen_ids:   set[int] = set()
        # Type-scoped search el awel (e.g. only search "data structure" nodes for a "data structure" concept)da by reduces false positives w improves relevance. Fall back to global search if type-specific index is empty or missing.
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

        # Stage 3, cross-encoder reranking
        pairs = [(query_text, _node_to_doc(c[0])) for c in candidates]
        raw_scores: np.ndarray = np.array(cross_encoder.predict(
            pairs, show_progress_bar=False))

        # NLI models (e.g. nli-deberta-v3-small) return shape (N, 3):
        #   col 0 = contradiction, col 1 = entailment, col 2 = neutral
        # Apply softmax across all 3 columns so the result gh7gh is a true
        # probability in [0, 1].  Use the entailment column as confidence.
        #
        # Single-score models (e.g. ms-marco) return sh7rsj shape (N,) as raw
        # logits — apply sigmoid to map to [0, 1].
        if raw_scores.ndim == 2:
            exp = np.exp(raw_scores - raw_scores.max(axis=1, keepdims=True))
            scores = (exp / exp.sum(axis=1, keepdims=True))[:, 1].astype(float)
        else:
            scores = np.array([_sigmoid(float(s)) for s in raw_scores])

        best_pos   = int(np.argmax(scores))
        best_score = float(scores[best_pos])
        best_node  = candidates[best_pos][0]

        if best_score < MATCH_THRESHOLD:
            summary["no_match"] += 1
            details.append(_miss_record(concept, best_node, best_score))
            continue

        new_mappings.append(ConceptNodeMapping(
            concept_id=concept.id, node_id=best_node.id,
            confidence=round(best_score, 4), match_type="semantic",
        ))
        summary["semantic"] += 1
        details.append(_match_record(concept, best_node, "semantic",
                                     round(best_score, 4)))

    for mapping in new_mappings:
        session.add(mapping)
    session.commit()

    return summary, details


# helper functions to format the match/miss details for each concept, used for debugging and analysis. 
# el _match_record function betakhod concept w node w match_type w confidence w terga3 dict feha el ma3loumat el mohema 3an el match (e.g. concept name w type, node name w type w source, match type, confidence score).
def _match_record(concept: Concept, node: KnowledgeNode,
                  match_type: str, confidence: float) -> dict:
    return {
        "concept_name": concept.name,
        "concept_type": concept.concept_type or "unknown",
        "match_type":   match_type,
        "node_id":  node.id,
        "node_name":    node.name,
        "node_type": node.concept_type or "unknown",
        "node_source":  node.source,
        "confidence":confidence,
        "best_miss_name":  None,
        "best_miss_score": None,
    }

#  el _miss_record function betakhod concept w best_node w best_score (even law mafeesh match akbar men el threshold) w terga3 dict feha el ma3loumat el mohema 3an el miss (e.g. concept name w type, best matching node name w source w score).
def _miss_record(concept: Concept,
                 best_node: Optional[KnowledgeNode],
                 best_score: Optional[float]) -> dict:
    return {
        "concept_name": concept.name,
        "concept_type": concept.concept_type or "unknown",
        "match_type":   "no_match",
        "node_id":None,
        "node_name": None,
        "node_type":None,
        "node_source": None,
        "confidence":None,
        "best_miss_name":  best_node.name if best_node else None,
        "best_miss_score": round(best_score, 4) if best_score is not None else None,
    }

# helper function to show the existing mappings for a course, used when --show-mapped flag is set. \
# bygeb kol el concepts lel course w el mappings el mawgodeen fe database w yerga3hom fe format readable 3shan n3raf n7assan fe eh w n7assan el models w el data.
def show_existing_mappings(
    courses:     list[Course],
    session:     Session,
    nodes_by_id: dict[int, KnowledgeNode],
) -> None:
    for course in courses:
        concepts: list[Concept] = (
            session.query(Concept)
            .filter(Concept.course_id == course.id)
            .all()
        )
        concept_by_id = {c.id: c for c in concepts}
        mappings = (
            session.query(ConceptNodeMapping)
            .filter(ConceptNodeMapping.concept_id.in_(
                list(concept_by_id.keys())))
            .all()
        )
        unmapped = [c for c in concepts
                    if c.id not in {m.concept_id for m in mappings}]

        print(f"=== Course '{course.name}' "
              f"— {len(mappings)} mapped, {len(unmapped)} unmapped ===")

        if mappings:
            print(f"\n  MAPPED ({len(mappings)}):")
            print(f"  {'─'*70}")
            for m in sorted(mappings,
                            key=lambda x: concept_by_id[x.concept_id].name):
                concept   = concept_by_id[m.concept_id]
                node      = nodes_by_id.get(m.node_id)
                tag = {"exact_name": "exact ", "exact_alias": "alias ",
                       "semantic": f"  {m.confidence:.2f}"}.get(m.match_type, "      ")
                node_name   = node.name   if node else f"[node_id={m.node_id}]"
                node_source = node.source if node else "?"
                print(f"  ✓ [{tag}]  {concept.name:<32}  "
                      f"→  {node_name:<32}  [{node_source:<10}]")

        if unmapped:
            print(f"\n  UNMAPPED ({len(unmapped)}):")
            print(f"  {'─'*70}")
            for c in sorted(unmapped, key=lambda x: x.name):
                print(f"  ✗ {c.name:<38}  [{c.concept_type}]")
        print()


# el main function, byparse el command line arguments (e.g. --course-id, --course-name, --show-mapped), byconnect lel database w bygeb el courses el mawgodeen based on el arguments. bygeb kaman kol el knowledge nodes w bybuild el alias lookup w el FAISS indices. ba3d kda byloop 3la kol course w bycall map_concepts_for_course w byprint el summary w details lel mapping. law --show-mapped flag met3amelsh, hayshow el existing mappings fe database 3shan n3raf n7assan fe eh w n7assan el models w el data.
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
        print(f"  Mode         : show existing mappings")
    print(f"{'='*60}\n")

    engine = create_engine(CONCEPT_DB_URL)

    with Session(engine) as session:
        # Resolve courses, course.id is VARCHAR UUID
        if args.course_id:
            # --course-id accepts a UUID string
            course = session.get(Course, str(args.course_id))
            if course is None:
                print(f"ERROR: course_id='{args.course_id}' not found.",
                      file=sys.stderr)
                sys.exit(1)
            courses: list[Course] = [course]
        elif args.course_name:
            course = (
                session.query(Course)
                .filter(Course.name == args.course_name)
                .first()
            )
            if course is None:
                print(f"ERROR: course '{args.course_name}' not found.",
                      file=sys.stderr)
                sys.exit(1)
            courses = [course]
        else:
            courses = session.query(Course).all()

        print(f"[courses] Processing {len(courses)} course(s):")
        for c in courses:
            print(f"  • {c.name}  (id={c.id[:8]}...)")

        if args.show_mapped:
            nodes: list[KnowledgeNode] = session.query(KnowledgeNode).all()
            nodes_by_id = {n.id: n for n in nodes}
            print()
            show_existing_mappings(courses, session, nodes_by_id)
            return

        nodes: list[KnowledgeNode] = session.query(KnowledgeNode).all()
        session.expunge_all()

    if not nodes:
        print("ERROR: knowledge_nodes is empty. "
              "Run build_knowledge_graph.py first.", file=sys.stderr)
        sys.exit(1)

    node_count   = len(nodes)
    nodes_by_id  = {n.id: n for n in nodes}
    alias_lookup = _build_alias_lookup(nodes)
    print(f"[graph] {node_count} nodes, {len(alias_lookup)} alias entries.")

    print("\n[embed] Loading bi-encoder ...")
    from sentence_transformers import SentenceTransformer
    bi_encoder = SentenceTransformer(BI_ENCODER_MODEL)
    # et2aked el awal mn el cache
    if _cache_valid(node_count):
        print("[embed] Cache hit — loading from disk.")
        node_ids_arr, node_emb_arr = _load_cache()
    else:
        print(f"[embed] Cache miss — embedding {node_count} nodes ...")
        docs = [_node_to_doc(n) for n in nodes]
        node_emb_arr = bi_encoder.encode(
            docs, normalize_embeddings=True,
            batch_size=64, show_progress_bar=True,
        ).astype(np.float32)
        # node_ids are integers — store as int32
        node_ids_arr = np.array([n.id for n in nodes], dtype=np.int32)
        _save_cache(node_ids_arr, node_emb_arr, node_count)
        print(f"[embed] Cached to {CACHE_DIR}/")

    print("[index] Building FAISS indices ...")
    type_indices, global_index = _build_indices(
        node_ids_arr, node_emb_arr, nodes_by_id)

    print("\n[rerank] Loading cross-encoder ...")
    from sentence_transformers.cross_encoder import CrossEncoder
    cross_encoder = CrossEncoder(CROSS_ENCODER_MODEL)

    print()
    with Session(engine) as session: #etba3 el data
        for course in courses:
            print(f"=== Mapping '{course.name}' ===")
            summary, details = map_concepts_for_course(
                course_id=course.id,
                session=session,
                bi_encoder=bi_encoder,
                cross_encoder=cross_encoder,
                nodes=nodes,
                nodes_by_id=nodes_by_id,
                alias_lookup=alias_lookup,
                type_indices=type_indices,
                global_index=global_index,
            )
            _print_mapping_details(details)
            print(f"  [result] exact_name={summary.get('exact_name',0)}  "
                  f"exact_alias={summary.get('exact_alias',0)}  "
                  f"semantic={summary.get('semantic',0)}  "
                  f"no_match={summary.get('no_match',0)}")
            print()

    print("[done] Mapping complete.")


def _print_mapping_details(details: list[dict]) -> None:
    if not details:
        return
    matched   = [d for d in details if d["match_type"] != "no_match"]
    unmatched = [d for d in details if d["match_type"] == "no_match"]
    if matched:
        print(f"\n  MATCHED ({len(matched)}):")
        print(f"  {'─'*70}")
        for d in matched:
            tag = {"exact_name": "exact ", "exact_alias": "alias ",
                   "semantic": f"  {d['confidence']:.2f}"}.get(d["match_type"], "      ")
            src = f"[{d['node_source']:<10}]" if d["node_source"] else ""
            print(f"  ✓ [{tag}]  {d['concept_name']:<32}  "
                  f"→  {d['node_name']:<32}  {src}")
    if unmatched:
        print(f"\n  NO MATCH ({len(unmatched)}):")
        print(f"  {'─'*70}")
        for d in unmatched:
            miss = ""
            if d["best_miss_name"]:
                miss = (f"  (best: '{d['best_miss_name']}' "
                        f"score={d['best_miss_score']:.2f})")
            print(f"  ✗ {d['concept_name']:<38}  [{d['concept_type']}]{miss}")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Map extracted concepts to knowledge graph nodes."
    )
    group = parser.add_mutually_exclusive_group()
    # --course-id now takes a UUID string, not an integer
    group.add_argument("--course-id",   type=str,
                       help="Target a single course by UUID")
    group.add_argument("--course-name", type=str,
                       help="Target a single course by name")
    parser.add_argument(
        "--show-mapped", action="store_true",
        help="Print existing mappings without running models.",
    )
    main(parser.parse_args())