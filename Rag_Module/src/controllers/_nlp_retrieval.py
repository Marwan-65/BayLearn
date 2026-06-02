"""
NLPController — Retrieval mixin

Contains retrieve_sources() — the 7-layer retrieval pipeline:
    multi-query -> dense search -> BM25 -> RRF fusion -> rerank ->
    filter -> intent-aware compression.

Also hosts _has_usable_text() and _has_math_content() helpers.
"""

import math
import re
import time
from typing import Optional

from compressors import AdaptiveContextualCompressor
from stores.LLM.LLMEnums import DocumentTypeEnum


def _cosine(a, b) -> float:
    """Cosine similarity between two equal-length vectors (lists)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0 or nb == 0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


class _NLPRetrievalMixin:

    # In-memory caches per project, lazily built on first retrieval.
    # Invalidated on re-index by clearing both from _NLPIndexingMixin.
    #   _image_index_cache[project_id]      = {page: [image chunks]}
    #   _chunks_by_id_cache[project_id]     = {chunk_id: chunk_dict}    (all types)
    #   _chunks_sorted_cache[project_id]    = list of chunks sorted by chunk_id
    _image_index_cache: dict = {}
    _chunks_by_id_cache: dict = {}
    _chunks_sorted_cache: dict = {}

    def _build_chunk_caches(self, project_id: str):
        """Populate all three caches in one pass."""
        if project_id in _NLPRetrievalMixin._image_index_cache:
            return  # already built

        img_index: dict = {}
        by_id: dict = {}
        try:
            data = self.chunk_repository._load()  # sync read
            raw_chunks = data.get(project_id, [])
            sorted_chunks = sorted(raw_chunks, key=lambda c: c.get("chunk_id", 0))
            for c in sorted_chunks:
                meta = c.get("metadata", {}) or {}
                cid = c.get("chunk_id")
                entry = {
                    "chunk_id": cid,
                    "text": c.get("text", ""),
                    "metadata": meta,
                }
                if cid is not None:
                    by_id[cid] = entry
                if meta.get("chunk_type") == "image":
                    page = meta.get("page")
                    if page is not None:
                        img_index.setdefault(page, []).append(entry)
            _NLPRetrievalMixin._chunks_sorted_cache[project_id] = sorted_chunks
        except Exception as e:
            self.logger.warning(f"Could not build chunk caches: {e}")
            _NLPRetrievalMixin._chunks_sorted_cache[project_id] = []

        _NLPRetrievalMixin._image_index_cache[project_id] = img_index
        _NLPRetrievalMixin._chunks_by_id_cache[project_id] = by_id
        self.logger.info(
            f"Chunk caches for {project_id}: {len(by_id)} total, "
            f"{sum(len(v) for v in img_index.values())} images across "
            f"{len(img_index)} pages"
        )

    def _get_image_chunks_by_page(self, project_id: str) -> dict:
        self._build_chunk_caches(project_id)
        return _NLPRetrievalMixin._image_index_cache.get(project_id, {})

    def _get_neighbor_text_chunks(
        self, project_id: str, image_chunk_id: int,
        radius: int = 2, max_neighbors: int = 2,
    ) -> list:
        """Return up to `max_neighbors` text chunks within ±`radius` chunk-ids
        of the given image chunk. Used to attach caption / surrounding-paragraph
        context to a promoted image so the LLM can explain how the figure
        relates to the concept (rather than just describing pixels)."""
        self._build_chunk_caches(project_id)
        by_id = _NLPRetrievalMixin._chunks_by_id_cache.get(project_id, {})
        if not by_id or image_chunk_id is None:
            return []

        # Walk outward from the image's id, alternating before/after.
        candidates = []
        for offset in range(1, radius + 1):
            for delta in (-offset, offset):
                cid = image_chunk_id + delta
                entry = by_id.get(cid)
                if not entry:
                    continue
                if entry["metadata"].get("chunk_type") != "text":
                    continue
                if not (entry["text"] or "").strip():
                    continue
                candidates.append(entry)
                if len(candidates) >= max_neighbors:
                    return candidates
        return candidates

    @staticmethod
    def _has_usable_text(result: dict, min_length: int = 20) -> bool:
        """
        Replacement for the old chunk_type=="image" filter. Keeps a chunk
        if it has any non-trivial text content, regardless of whether it
        came from a text block, an OCR'd image caption, or a table.
        """
        text = result.get("payload", {}).get("text", "") or ""
        return len(text.strip()) >= min_length

    @staticmethod
    def _has_math_content(text: str, threshold: float = 0.02) -> bool:
        """True if the text contains a significant density of math symbols."""
        math_symbols = set(
            "=+<>^{}[]()|\\"
            "\u222b\u2211\u220f\u221a\u221e\u2248\u2260\u2264\u2265"
            "\u00b1\u00d7\u00f7\u2202\u2207\u0394"
            "\u03bb\u03bc\u03c3\u03b8\u03c6\u03c0"
            "\u03b1\u03b2\u03b3\u03b4\u03b5\u03b6\u03b7\u03b9\u03ba"
            "\u03bd\u03be\u03c1\u03c4\u03c5\u03c8\u03c9"
        )
        latex_count = len(re.findall(r"[\\^_{}]|\b\d+[a-z]\b", text))
        symbol_count = sum(1 for c in text if c in math_symbols)
        total_indicators = symbol_count + latex_count
        if not text:
            return False
        return (total_indicators / len(text)) >= threshold

    def retrieve_sources(
        self,
        project_id: str,
        question: str,
        limit: int = 5,
        score_threshold: float = 0.4,
        intent: str = "rag_only",
        enable_multi_query: Optional[bool] = None,
        enable_hybrid: Optional[bool] = None,
        enable_reranker: Optional[bool] = None,
        enable_compression: Optional[bool] = None,
    ):
        """
        Multi-file dispatcher. `project_id` may be a single id or a comma-
        separated list of file ids (the frontend joins the selected files).

        - One id  -> runs the full per-collection pipeline unchanged.
        - Many ids -> runs the pipeline per file and merges the results by score,
          so chat is grounded in the union of the selected files.
        """
        ids = [p.strip() for p in str(project_id).split(",") if p.strip()]
        if len(ids) <= 1:
            return self._retrieve_sources_single(
                ids[0] if ids else project_id, question, limit, score_threshold,
                intent, enable_multi_query, enable_hybrid, enable_reranker,
                enable_compression,
            )

        per_file = [
            self._retrieve_sources_single(
                pid, question, limit, score_threshold, intent,
                enable_multi_query, enable_hybrid, enable_reranker,
                enable_compression,
            )
            for pid in ids
        ]
        ok = [r for r in per_file if r and "filtered_results" in r]
        if not ok:
            # Surface a real result-shaped error if any, else generic.
            for r in per_file:
                if r and r.get("error"):
                    return r
            return {"error": "no_relevant_sources", "query": question, "timings": {}}

        merged = []
        for r in ok:
            merged.extend(r["filtered_results"])
        # Higher score first; reranked/RRF lists expose rrf_score, dense uses score.
        merged.sort(key=lambda x: x.get("rrf_score", x.get("score", 0)), reverse=True)
        merged = merged[:limit]

        combined_timings = {}
        for r in ok:
            for k, v in (r.get("timings") or {}).items():
                if isinstance(v, (int, float)):
                    combined_timings[k] = combined_timings.get(k, 0) + v
        fuse_labels = sorted({lbl for r in ok for lbl in (r.get("fuse_labels") or [])})

        return {
            "filtered_results": merged,
            "query_vector": ok[0].get("query_vector"),
            "query_variants": ok[0].get("query_variants", [question]),
            "multi_query_used": any(r.get("multi_query_used") for r in ok),
            "reranker_used": any(r.get("reranker_used") for r in ok),
            "hybrid_used": any(r.get("hybrid_used") for r in ok),
            "bm25_count": sum(r.get("bm25_count", 0) for r in ok),
            "fuse_labels": fuse_labels,
            "compression_used": any(r.get("compression_used") for r in ok),
            "compression_ratios": [1.0] * len(merged),
            "timings": combined_timings,
            "files_merged": len(ok),
        }

    def _retrieve_sources_single(
        self,
        project_id: str,
        question: str,
        limit: int = 5,
        score_threshold: float = 0.4,
        intent: str = "rag_only",
        enable_multi_query: Optional[bool] = None,
        enable_hybrid: Optional[bool] = None,
        enable_reranker: Optional[bool] = None,
        enable_compression: Optional[bool] = None,
    ):
        """
        Run the full retrieval pipeline WITHOUT generating an LLM answer.

        Each enable_* flag accepts None/True/False. None means "use the
        value from config". True/False force the technique on or off for
        this call only, which is what /evaluate/ablation uses to toggle
        techniques across runs without restarting the server.
        """
        collection_name = self.create_collection_name(project_id)
        settings = self.app_settings
        timings = {}

        multi_query_enabled = (
            getattr(settings, "MULTI_QUERY_ENABLED", False)
            if enable_multi_query is None else enable_multi_query
        )
        compression_enabled = (
            getattr(settings, "COMPRESSION_ENABLED", False)
            if enable_compression is None else enable_compression
        )
        reranker_enabled_flag = (
            getattr(settings, "RERANKER_ENABLED", False)
            if enable_reranker is None else enable_reranker
        )
        use_reranker = (
            reranker_enabled_flag and self.reranker_client is not None
        )
        hybrid_requested = (
            getattr(settings, "BM25_ENABLED", False)
            if enable_hybrid is None else enable_hybrid
        )
        hybrid_enabled = (
            hybrid_requested
            and self.bm25_client is not None
            and self.bm25_client.index_exists(project_id)
        )

        reranker_multiplier = (
            getattr(settings, "RERANKER_OVER_RETRIEVAL_MULTIPLIER", 3)
            if use_reranker else 1
        )
        compression_multiplier = (
            getattr(settings, "COMPRESSION_RETRIEVAL_MULTIPLIER", 2)
            if compression_enabled else 1
        )
        hybrid_multiplier = (
            getattr(settings, "HYBRID_OVER_RETRIEVAL_MULTIPLIER", 2)
            if hybrid_enabled else 1
        )
        retrieval_limit = limit * max(
            reranker_multiplier, compression_multiplier, hybrid_multiplier
        )

        self.logger.info(
            f"Retrieval: limit={limit}, budget={retrieval_limit}, "
            f"multi_query={multi_query_enabled}, hybrid={hybrid_enabled}, "
            f"reranker={use_reranker}, compression={compression_enabled}, "
            f"intent={intent}"
        )

        if (
            self.bm25_client is not None
            and hybrid_requested
            and not hybrid_enabled
        ):
            self.logger.warning(
                f"BM25 index missing for project {project_id}; using dense-only. "
                "Re-run /index/push to build it."
            )

        # ---- STEP 1: Multi-query (RAG-Fusion) ----
        query_count = getattr(settings, "MULTI_QUERY_COUNT", 3)
        query_variants = [question]

        if multi_query_enabled:
            mq_prompt = (
                f"Generate {query_count} different versions of the following "
                "question to help find relevant study materials. Each version "
                "should approach the topic from a different angle or use "
                "different keywords.\n"
                "Return ONLY the questions, one per line. Do not number them "
                "or add any other text.\n\n"
                f"Original question: {question}"
            )
            t0 = time.time()
            try:
                raw_variants = self.generation_client.generate_text(
                    prompt=mq_prompt,
                    chat_history=[],
                    max_output_tokens=200,
                    temperature=0.7,
                )
                if raw_variants:
                    lines = [
                        line.strip()
                        for line in raw_variants.strip().split("\n")
                        if line.strip() and len(line.strip()) > 10
                    ]
                    query_variants.extend(lines[:query_count])
            except Exception as e:
                self.logger.warning(f"Multi-query generation failed: {e}")
            timings["multi_query_generation_ms"] = round((time.time() - t0) * 1000)

        # ---- STEP 2: Dense search on each variant ----
        t0 = time.time()
        all_dense_results = []
        source_labels = []
        query_vector = None

        for i, variant in enumerate(query_variants):
            qv = self.embedding_client.embed_text(
                text=variant,
                document_type=DocumentTypeEnum.QUERY.value,
            )
            if not qv:
                continue
            if i == 0:
                query_vector = qv
            results = self.vectordb_client.search_by_vector(
                collection_name=collection_name,
                query_vector=qv,
                limit=retrieval_limit,
            )
            if results:
                all_dense_results.append(results)
                source_labels.append(f"dense_q{i}")

        timings["dense_search_ms"] = round((time.time() - t0) * 1000)

        if not all_dense_results:
            return {"error": "No relevant documents found"}

        # ---- STEP 3: BM25 sparse search ----
        bm25_results = []
        if hybrid_enabled:
            t0 = time.time()
            try:
                bm25_results = self.bm25_client.search(
                    project_id=project_id,
                    query=question,
                    top_k=retrieval_limit,
                )
            except Exception as e:
                self.logger.warning(f"BM25 search failed: {e}")
                bm25_results = []
            timings["bm25_search_ms"] = round((time.time() - t0) * 1000)

        # ---- STEP 3.5: RRF fusion ----
        from stores.bm25.fusion import reciprocal_rank_fusion

        ranked_lists = all_dense_results[:]
        fuse_labels = source_labels[:]
        if bm25_results:
            ranked_lists.append(bm25_results)
            fuse_labels.append("bm25")

        t0 = time.time()
        if len(ranked_lists) > 1:
            search_results = reciprocal_rank_fusion(
                ranked_lists=ranked_lists,
                k=getattr(settings, "RRF_K", 60),
                top_k=retrieval_limit,
                id_key="id",
                source_names=fuse_labels,
            )
        else:
            search_results = ranked_lists[0] if ranked_lists else []
        timings["rrf_fusion_ms"] = round((time.time() - t0) * 1000)

        if not search_results:
            return {"error": "No relevant documents found"}

        # ---- STEP 3.75: Cross-encoder rerank ----
        t0 = time.time()
        if use_reranker:
            try:
                search_results = self.reranker_client.rerank(
                    query=question,
                    documents=search_results,
                    top_k=limit,
                )
            except Exception as e:
                self.logger.warning(
                    f"Reranker failed, falling back to vector order: {e}"
                )
                search_results = search_results[:limit]
        else:
            search_results = search_results[:limit]
        timings["reranking_ms"] = round((time.time() - t0) * 1000)

        # ---- STEP 4: Filter by usable-text + score threshold ----
        search_results = [
            r for r in search_results if self._has_usable_text(r, min_length=20)
        ]

        if "rrf_score" in (search_results[0] if search_results else {}):
            filtered_results = [
                r for r in search_results if r.get("rrf_score", 0) > 0
            ]
        else:
            filtered_results = [
                r for r in search_results if r["score"] >= score_threshold
            ]

        if not filtered_results:
            return {
                "error": "no_relevant_sources",
                "query": question,
                "multi_query_used": multi_query_enabled,
                "query_variants": query_variants,
                "reranker_used": use_reranker,
                "hybrid_used": hybrid_enabled,
                "timings": timings,
            }

        # ---- STEP 4.25: Same-page image promotion ----
        # If a top text chunk comes from page N and an image chunk exists on
        # page N that wasn't already retrieved, add it to the result set so
        # the answer can reference (and the frontend render) the figure.
        # Caps total promotions to avoid drowning out text sources.
        promote_images = getattr(settings, "SAME_PAGE_IMAGE_PROMOTION", True)
        max_promote = getattr(settings, "SAME_PAGE_IMAGE_MAX", 2)
        images_promoted = 0
        if promote_images and intent == "rag_only":
            t0 = time.time()
            existing_ids = {r.get("id") for r in filtered_results}
            existing_ids.update(
                r["payload"].get("chunk_id") for r in filtered_results
                if r.get("payload")
            )
            pages_in_results = []
            seen_pages = set()
            for r in filtered_results:
                page = r["payload"].get("page")
                if page is not None and page not in seen_pages:
                    pages_in_results.append(page)
                    seen_pages.add(page)

            page_to_images = self._get_image_chunks_by_page(project_id)
            neighbor_radius = getattr(settings, "SAME_PAGE_IMAGE_NEIGHBOR_RADIUS", 2)
            neighbors_per_image = getattr(
                settings, "SAME_PAGE_IMAGE_NEIGHBORS_PER_IMAGE", 2
            )
            # An image is only promoted if its description embeds close enough
            # to the question. Stops the system from showing a "transition
            # diagram" just because it happens to live on the same page as a
            # relevant text chunk.
            img_min_sim = getattr(
                settings, "IMAGE_PROMOTION_MIN_SIMILARITY", 0.30
            )

            # Score every candidate image by (image_description ⋅ query) and
            # rank globally — not page-by-page — so the most relevant figures
            # in the result set win the promotion budget.
            candidates = []  # [(similarity, page, img_chunk)]
            for page in pages_in_results:
                for img in page_to_images.get(page, []):
                    cid = img["chunk_id"]
                    if cid in existing_ids:
                        continue
                    img_text = (img.get("text") or "").strip()
                    if not img_text:
                        continue
                    if query_vector is None:
                        sim = 0.0
                    else:
                        try:
                            img_vec = self.embedding_client.embed_text(
                                text=img_text,
                                document_type=DocumentTypeEnum.DOCUMENT.value,
                            )
                            sim = _cosine(query_vector, img_vec)
                        except Exception as e:
                            self.logger.warning(
                                f"Failed to embed image desc for promotion: {e}"
                            )
                            sim = 0.0
                    if sim < img_min_sim:
                        self.logger.info(
                            f"Skipping image on page {page} "
                            f"(sim={sim:.2f} < {img_min_sim}): "
                            f"{img['metadata'].get('image_path')}"
                        )
                        continue
                    candidates.append((sim, page, img))

            # Highest-similarity images first. This means a relevant image on
            # page 43 wins over a tangentially-similar one on page 42 even if
            # both pages had top text matches.
            candidates.sort(key=lambda t: -t[0])

            promoted = []
            for sim, page, img in candidates:
                if images_promoted >= max_promote:
                    break
                cid = img["chunk_id"]

                # Pull caption neighbors and FOLD them into the image's
                # own text body. The LLM gets a single image source with
                # both the visual description AND the surrounding paragraph,
                # so it can't mistake caption text for a separate figure.
                neighbors = self._get_neighbor_text_chunks(
                    project_id, cid,
                    radius=neighbor_radius,
                    max_neighbors=neighbors_per_image,
                )
                caption_blocks = []
                for nb in neighbors:
                    nb_cid = nb["chunk_id"]
                    if nb_cid in existing_ids:
                        continue
                    caption_blocks.append((nb["text"] or "").strip())
                    # Mark as consumed so we don't re-emit this text as a
                    # separate text source if the dense search later picks
                    # it up by accident.
                    existing_ids.add(nb_cid)

                merged_text = (img.get("text") or "").strip()
                if caption_blocks:
                    merged_text = (
                        f"{merged_text}\n\n"
                        f"--- Surrounding paragraph (page {page}) ---\n"
                        + "\n\n".join(caption_blocks)
                    )

                promoted.append({
                    "id": cid,
                    "score": sim,
                    "payload": img["metadata"] | {"text": merged_text},
                    "promoted_from_page": page,
                    "image_query_similarity": round(sim, 3),
                    "caption_neighbors_folded": len(caption_blocks),
                })
                existing_ids.add(cid)
                images_promoted += 1

            if promoted:
                filtered_results = filtered_results + promoted
                self.logger.info(
                    f"Promoted {len(promoted)} image(s) "
                    f"(sims: {[round(p['image_query_similarity'], 2) for p in promoted]}, "
                    f"captions folded: {[p['caption_neighbors_folded'] for p in promoted]}) "
                    f"from pages {[p['promoted_from_page'] for p in promoted]}. "
                    f"({len(candidates)} of {sum(len(page_to_images.get(p, [])) for p in pages_in_results)} "
                    f"page-images passed sim>={img_min_sim} gate.)"
                )
            elif candidates:
                self.logger.info(
                    f"{len(candidates)} image candidate(s) passed sim>={img_min_sim} "
                    f"but max_promote={max_promote} prevented adding any."
                )
            else:
                total = sum(len(page_to_images.get(p, [])) for p in pages_in_results)
                if total:
                    self.logger.info(
                        f"All {total} same-page image(s) filtered: none reached "
                        f"sim>={img_min_sim} for query."
                    )
            timings["image_promotion_ms"] = round((time.time() - t0) * 1000)

        # ---- STEP 4.5: Intent-aware contextual compression ----
        t0 = time.time()
        compression_ratios = []

        if compression_enabled:
            compressor = AdaptiveContextualCompressor(
                embedding_client=self.embedding_client,
                similarity_threshold=getattr(
                    settings, "COMPRESSION_SIMILARITY_THRESHOLD", 0.5
                ),
                min_chunk_length=getattr(
                    settings, "COMPRESSION_MIN_CHUNK_LENGTH", 50
                ),
                min_keep_ratio=getattr(
                    settings, "COMPRESSION_MIN_KEEP_RATIO", 0.3
                ),
                skip_single_chunk=getattr(
                    settings, "COMPRESSION_SKIP_SINGLE_CHUNK", True
                ),
            )

            chunks_for_compression = []
            protected_indices = set()

            for idx, r in enumerate(filtered_results):
                chunk_type = r["payload"].get("chunk_type", "text")
                text = r["payload"].get("text", "")

                # Image chunks carry the figure description — never compress.
                if chunk_type == "image":
                    protected_indices.add(idx)
                    continue

                if intent == "equation_from_context" and chunk_type in (
                    "equation", "table"
                ):
                    protected_indices.add(idx)
                    continue
                if intent == "equation_from_context" and self._has_math_content(text):
                    protected_indices.add(idx)
                    continue

                chunks_for_compression.append({
                    "text": text,
                    "score": r["score"],
                    "metadata": r["payload"],
                    "_original_idx": idx,
                })

            if chunks_for_compression:
                compressed_chunks = compressor.compress(
                    chunks=chunks_for_compression,
                    query_embedding=query_vector,
                )
                for compressed in compressed_chunks:
                    orig_idx = compressed["_original_idx"]
                    filtered_results[orig_idx]["payload"]["text"] = compressed["text"]
                    compression_ratios.append(
                        compressed.get("compression_ratio", 1.0)
                    )

            for _ in protected_indices:
                compression_ratios.append(1.0)
        else:
            compression_ratios = [1.0] * len(filtered_results)

        timings["compression_ms"] = round((time.time() - t0) * 1000)

        return {
            "filtered_results": filtered_results,
            "query_vector": query_vector,
            "query_variants": query_variants,
            "multi_query_used": multi_query_enabled,
            "reranker_used": use_reranker,
            "hybrid_used": hybrid_enabled,
            "bm25_count": len(bm25_results) if hybrid_enabled else 0,
            "fuse_labels": fuse_labels,
            "compression_used": compression_enabled,
            "compression_ratios": compression_ratios,
            "timings": timings,
        }
