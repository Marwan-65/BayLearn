"""
NLPController — Indexing mixin

Contains index_project(), which handles:
  - dense embedding + Qdrant insertion
  - Contextual Retrieval (Anthropic 2024) with on-disk cache
  - BM25 sparse index build

This file is not intended to be used standalone. It is mixed into
NLPController via multiple inheritance in controllers/nlp.py.
"""

from stores.LLM.LLMEnums import DocumentTypeEnum


class _NLPIndexingMixin:

    async def index_project(self, project_id: str, do_reset: bool = False):
        collection_name = self.create_collection_name(project_id)
        chunks = await self.chunk_repository.get_chunks(project_id)

        if not chunks:
            return 0

        self.vectordb_client.create_collection(
            collection_name=collection_name,
            embedding_size=self.embedding_client.embedding_size,
            do_reset=do_reset,
        )

        contextual_retrieval_enabled = getattr(
            self.app_settings, "CONTEXTUAL_RETRIEVAL_ENABLED", False
        )
        cr_max_tokens = getattr(
            self.app_settings, "CONTEXTUAL_RETRIEVAL_MAX_TOKENS", 100
        )

        texts_to_embed = []
        cache_hits = 0
        cache_misses = 0

        for chunk in chunks:
            doc_title = (
                chunk.metadata.get("doc_title")
                or chunk.metadata.get("source")
                or "Unknown document"
            )
            page = chunk.metadata.get("page", "")
            section = (
                chunk.metadata.get("section_heading")
                or chunk.metadata.get("section")
                or ""
            )

            if contextual_retrieval_enabled:
                context_desc = None

                if self.contextual_cache is not None:
                    context_desc = self.contextual_cache.get(
                        doc_title=doc_title,
                        section=section,
                        chunk_text=chunk.text,
                    )
                    if context_desc:
                        cache_hits += 1

                if context_desc is None:
                    cache_misses += 1
                    cr_prompt = (
                        f"Document: {doc_title}\n"
                        f"Page: {page}\n"
                        f"Section: {section}\n\n"
                        f"Chunk content:\n{chunk.text}\n\n"
                        "Write a brief (1-2 sentence) description that "
                        "situates this chunk within the document. Explain "
                        "what topic it covers and how it relates to the "
                        "section. This will be prepended to the chunk to "
                        "improve search retrieval. Output ONLY the description."
                    )
                    try:
                        context_desc = self.generation_client.generate_text(
                            prompt=cr_prompt,
                            chat_history=[],
                            max_output_tokens=cr_max_tokens,
                            temperature=0.0,
                        )
                    except Exception as e:
                        self.logger.warning(
                            f"Contextual retrieval failed for chunk: {e}"
                        )
                        context_desc = None

                    if context_desc and self.contextual_cache is not None:
                        self.contextual_cache.set(
                            doc_title=doc_title,
                            section=section,
                            chunk_text=chunk.text,
                            description=context_desc.strip(),
                        )

                if context_desc:
                    contextual_text = (
                        f"{context_desc.strip()}\n\n"
                        f"Document: {doc_title} | Page: {page} | Section: {section}\n\n"
                        f"{chunk.text}"
                    )
                else:
                    contextual_text = (
                        f"Document: {doc_title} | Page: {page} | Section: {section}\n\n"
                        f"{chunk.text}"
                    )
            else:
                contextual_text = (
                    f"Document: {doc_title} | Page: {page} | Section: {section}\n\n"
                    f"{chunk.text}"
                )

            texts_to_embed.append(contextual_text)

        if contextual_retrieval_enabled and self.contextual_cache is not None:
            self.contextual_cache.flush()
            self.logger.info(
                f"Contextual cache: {cache_hits} hits, {cache_misses} misses "
                f"(cache size: {self.contextual_cache.size()})"
            )

        embeddings = [
            self.embedding_client.embed_text(
                text=t,
                document_type=DocumentTypeEnum.DOCUMENT.value,
            )
            for t in texts_to_embed
        ]

        record_ids = [c.chunk_id for c in chunks]

        success = self.vectordb_client.insert_many(
            collection_name=collection_name,
            texts=texts_to_embed,
            vectors=embeddings,
            metadata=[c.metadata for c in chunks],
            record_ids=record_ids,
        )
        if not success:
            return 0

        if self.bm25_client is not None and self.app_settings.BM25_ENABLED:
            payloads = [
                {"text": texts_to_embed[i], **(chunks[i].metadata or {})}
                for i in range(len(chunks))
            ]
            if do_reset:
                self.bm25_client.delete_index(project_id)
            self.bm25_client.build_index(
                project_id=project_id,
                texts=texts_to_embed,
                ids=record_ids,
                payloads=payloads,
            )

        return len(chunks)
