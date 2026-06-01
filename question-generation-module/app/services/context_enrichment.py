"""
Context Enrichment Layer
========================
Replaces the single-query + random.sample approach with:

  1. Difficulty-aware multi-query expansion
     Fire multiple targeted queries to the RAG module based on difficulty
     level so the retrieved chunks actually match what the LLM needs to
     produce that kind of question.

  2. Maximal Marginal Relevance (MMR) selection
     Instead of random sampling, greedily pick chunks that are
     (a) highly relevant to the query and (b) dissimilar to chunks
     already selected.  This guarantees concept coverage without
     redundancy.

     MMR formula (Carbonell & Goldstein, 1998):
       score(c) = λ · relevance(c, query)
                − (1−λ) · max_{s ∈ selected} sim(c, s)

     relevance(c, query) comes from the RAG module's own retrieval score.
     sim(c, s)            is cosine similarity on TF-IDF vectors of the
                          chunk texts — no embeddings model required.

Dependencies added: scikit-learn (TF-IDF + cosine_similarity)
"""

import logging
import re
from typing import List, Dict, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

# ── MMR balance: 0 = pure diversity, 1 = pure relevance ──────────────────────
MMR_LAMBDA = 0.65

# ── How many chunks to request per individual query ──────────────────────────
CHUNKS_PER_QUERY = 15

# ── Difficulty-aware query templates ─────────────────────────────────────────
# Each difficulty has a primary intent + a set of query variants.
# The RAG module is called once per variant; results are merged and
# deduplicated, then MMR-selected.

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
    """
    Return a list of search strings to fire at the RAG module.
    If the caller supplied a topic, prepend it to every template so the
    retrieval is anchored to the right section of the document.
    """
    base = DIFFICULTY_QUERIES.get(difficulty.lower(), DIFFICULTY_QUERIES["medium"])
    if topic:
        return [f"{topic} {q}" for q in base]
    return list(base)


def _deduplicate(chunks: List[dict]) -> List[dict]:
    """
    Merge lists of chunks coming from multiple queries.
    Keep the first occurrence (highest relevance score) for each chunk id.
    """
    seen: set = set()
    unique: List[dict] = []
    for chunk in chunks:
        cid = chunk.get("id")
        if cid not in seen:
            seen.add(cid)
            unique.append(chunk)
    return unique


def _mmr_select(
    chunks: List[dict],
    n: int,
    mmr_lambda: float = MMR_LAMBDA,
) -> List[dict]:
    """
    Greedy MMR selection.

    Parameters
    ----------
    chunks      : deduplicated list of chunks from the RAG module.
                  Each chunk must have a float "score" key (relevance).
    n           : how many chunks to select.
    mmr_lambda  : balance between relevance and diversity.

    Returns
    -------
    Up to n chunks ordered by the sequence in which MMR selected them.
    """
    if not chunks:
        return []

    n = min(n, len(chunks))

    # Extract texts for TF-IDF
    texts = [chunk.get("payload", {}).get("text", "") or "" for chunk in chunks]

    # Build TF-IDF matrix  (rows = chunks)
    try:
        vectorizer = TfidfVectorizer(stop_words="english", min_df=1)
        tfidf_matrix = vectorizer.fit_transform(texts)
        sim_matrix = cosine_similarity(tfidf_matrix)   # shape: (C, C)
    except ValueError:
        # All texts empty or too short — fall back to top-N by score
        logger.warning("MMR: TF-IDF failed (empty texts?), falling back to top-N.")
        return sorted(chunks, key=lambda c: c.get("score", 0), reverse=True)[:n]

    # Relevance array: use the RAG module's own retrieval score
    relevance = np.array([float(c.get("score", 0.0)) for c in chunks])

    selected_indices: List[int] = []
    remaining = list(range(len(chunks)))

    for _ in range(n):
        if not remaining:
            break

        if not selected_indices:
            # First pick: purely by relevance
            best = max(remaining, key=lambda i: relevance[i])
        else:
            # MMR score for each remaining candidate
            best_score = -np.inf
            best = remaining[0]
            for i in remaining:
                rel = relevance[i]
                # Max similarity to any already-selected chunk
                max_sim = max(sim_matrix[i, j] for j in selected_indices)
                mmr_score = mmr_lambda * rel - (1 - mmr_lambda) * max_sim
                if mmr_score > best_score:
                    best_score = mmr_score
                    best = i

        selected_indices.append(best)
        remaining.remove(best)

    return [chunks[i] for i in selected_indices]


class ContextEnrichmentLayer:
    """
    Wraps the ChunkFetcher and adds multi-query retrieval + MMR selection.

    Usage (in QuestionGenerationService):
        enricher = ContextEnrichmentLayer(chunk_fetcher)
        selected = await enricher.get_chunks(project_id, difficulty, topic, n=10)
    """

    def __init__(self, chunk_fetcher):
        self.chunk_fetcher = chunk_fetcher

    async def get_chunks(
        self,
        project_id: str,
        difficulty: str,
        topic: str | None,
        n: int = 10,
    ) -> Tuple[List[dict], dict]:
        """
        Retrieve and select the best n chunks for the given difficulty.

        Returns
        -------
        (selected_chunks, diagnostics)
          selected_chunks : list of chunk dicts ready for _prepare_context
          diagnostics     : dict with retrieval stats for logging/debugging
        """
        queries = _build_queries(difficulty, topic)
        logger.debug("Context enrichment queries for '%s': %s", difficulty, queries)

        # ── Fire all queries concurrently (gather pattern) ────────────────
        import asyncio
        results = await asyncio.gather(
            *[
                self.chunk_fetcher.fetch_relevant_chunks(
                    project_id=project_id,
                    query=q,
                    limit=CHUNKS_PER_QUERY,
                )
                for q in queries
            ],
            return_exceptions=True,
        )

        # Flatten, skip failed queries
        all_chunks: List[dict] = []
        query_hits: List[int] = []
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                logger.warning("Query %d failed: %s", i, res)
                query_hits.append(0)
            else:
                query_hits.append(len(res))
                all_chunks.extend(res)

        # ── Deduplicate ───────────────────────────────────────────────────
        unique_chunks = _deduplicate(all_chunks)

        # ── MMR selection ─────────────────────────────────────────────────
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
