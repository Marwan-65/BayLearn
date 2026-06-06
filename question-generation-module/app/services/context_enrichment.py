
import logging
from typing import List, Dict, Tuple
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

# MMR balance: 0 = pure diversity, 1 = pure relevance 
MMR_LAMBDA = 0.65
CHUNKS_PER_QUERY = 15

#Difficulty aware query templates
# Each difficulty has a primary intent + a set of query variants.
# The RAG module is called once per variant; results are merged and
# deduplicated, then selected for relevance with mmr

DIFFICULTY_QUERIES: Dict[str, List[str]] = {
    "easy": [
        "definition meaning what is",
        "basic concept terminology key term",
        "identify name list recall fact",
    ],
    "medium": [
        "explain how why describe relationship",
        "compare difference between summarize",
        "apply solve calculate demonstrate procedure",
    ],
    "hard": [
        "analyze evaluate justify critique argument",
        "synthesize design propose solution tradeoff",
        "distinguish underlying cause implication consequence",
    ],
}


def _build_queries(difficulty: str, topic: str | None) -> List[str]:
    base = DIFFICULTY_QUERIES.get(difficulty.lower(), DIFFICULTY_QUERIES["medium"])
    if topic:
        return [f"{topic} {q}" for q in base]
    return list(base)


def _deduplicate(chunks: List[dict]) -> List[dict]:
    seen: set = set()
    unique: List[dict] = []
    for chunk in chunks:
        cid = chunk.get("id")
        if cid not in seen:
            seen.add(cid)
            unique.append(chunk)
    return unique


def _mmr_select(chunks: List[dict],n: int,mmr_lambda: float = MMR_LAMBDA,) -> List[dict]:
    if not chunks:
        return []
    n = min(n, len(chunks))
    # here we extract texts for TF-IDF
    texts = [chunk.get("payload", {}).get("text", "") or "" for chunk in chunks]
    # then build TF-IDF matrix  
    try:
        vectorizer = TfidfVectorizer(stop_words="english", min_df=1)
        tfidf_matrix = vectorizer.fit_transform(texts)
        sim_matrix = cosine_similarity(tfidf_matrix)   # shape: (C, C)
    except ValueError:
        # all texts empty or too short
        logger.warning("MMR: TF-IDF failed (empty texts?), falling back to top-N.")
        return sorted(chunks, key=lambda c: c.get("score", 0), reverse=True)[:n]

    # relevance array use the RAG module's own retrieval score
    relevance = np.array([float(c.get("score", 0.0)) for c in chunks])

    selected_indices: List[int] = []
    remaining = list(range(len(chunks)))

    for _ in range(n):
        if not remaining:
            break

        if not selected_indices:
            # first pick only by relevance
            best = max(remaining, key=lambda i: relevance[i])
        else:
            # MMR score for each remaining candidate
            best_score = -np.inf
            best = remaining[0]
            for i in remaining:
                rel = relevance[i]
                # max similarity to any already selected chunk
                max_sim = max(sim_matrix[i, j] for j in selected_indices)
                mmr_score = mmr_lambda * rel - (1 - mmr_lambda) * max_sim
                if mmr_score > best_score:
                    best_score = mmr_score
                    best = i

        selected_indices.append(best)
        remaining.remove(best)

    return [chunks[i] for i in selected_indices]


class ContextEnrichmentLayer:
    def __init__(self, chunk_fetcher):
        self.chunk_fetcher = chunk_fetcher

    async def get_chunks(self,project_id: str,difficulty: str,topic: str | None,n: int = 10,) -> Tuple[List[dict], dict]:

        queries = _build_queries(difficulty, topic)
        logger.debug("context enrichment queries for '%s': %s", difficulty, queries)
        # Fire all queries at the same time 
        import asyncio
        results = await asyncio.gather(
            *[
                self.chunk_fetcher.fetch_relevant_chunks(
                    project_id=project_id,
                    topic=q,
                    limit=CHUNKS_PER_QUERY,
                )
                for q in queries
            ],
            return_exceptions=True,)

        # flatten returns and skip failed queries
        all_chunks: List[dict] = []
        query_hits: List[int] = []
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                logger.warning("Query %d failed: %s", i, res)
                query_hits.append(0)
            else:
                query_hits.append(len(res))
                all_chunks.extend(res)
        #removes duplicate chunks
        unique_chunks = _deduplicate(all_chunks)
        selected = _mmr_select(unique_chunks, n=n)

        diagnostics = {
            "difficulty": difficulty,
            "queries_fired": len(queries),
            "chunks_per_query": query_hits,
            "total_retrieved": len(all_chunks),
            "unique_after_dedup": len(unique_chunks),
            "selected_by_mmr": len(selected),
            "avg_relevance_score": round(
                float(np.mean([c.get("score", 0) for c in selected])), 3
            ) if selected else 0.0,
        }

        logger.info("Context enrichment: %s", diagnostics)
        return selected, diagnostics
