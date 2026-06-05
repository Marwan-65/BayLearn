from typing import List, Dict, Optional


def reciprocal_rank_fusion(
    ranked_lists: List[List[Dict]],
    k: int = 60, top_k: int = 10, id_key: str = "id", source_names: Optional[List[str]] = None,) -> List[Dict]:
    if source_names is None:
        source_names = []
    fused: Dict = {}

    for list_idx, doc_list in enumerate(ranked_lists):
        src = source_names[list_idx] if list_idx < len(source_names) else f"src{list_idx}"
        for rank, doc in enumerate(doc_list, start=1):
            doc_id = doc.get(id_key)
            if doc_id is None:
                continue
            contrib = 1.0 / (k + rank)

            if doc_id not in fused:
                merged = dict(doc)
                merged["rrf_score"] = contrib
                merged["rrf_sources"] = [src]
                merged[f"{src}_rank"] = rank
                merged[f"{src}_score"] = doc.get("score")
                fused[doc_id] = merged
            else:
                entry = fused[doc_id]
                entry["rrf_score"] += contrib
                entry["rrf_sources"].append(src)
                entry[f"{src}_rank"] = rank
                entry[f"{src}_score"] = doc.get("score")

    out = sorted(fused.values(), key=lambda d: d["rrf_score"], reverse=True)
    return out[:top_k]
