# this file makes a list of chunk objects and indexes them into Qdrant + BM25.
from stores.LLM.LLMEnums import DocumentTypeEnum
from controllers._nlp_retrieval import _NLPRetrievalMixin
from controllers._llm_calls import _contextual_desc_call

class _NLPIndexingMixin:
    async def index_project(self, project_id: str, chunks: list, do_reset: bool = False):
        collection_name = self.create_collection_name(project_id)
        if not chunks:
            return 0      
        _NLPRetrievalMixin._image_index_cache.pop(project_id, None)
        _NLPRetrievalMixin._chunks_by_id_cache.pop(project_id, None)
        _NLPRetrievalMixin._chunks_sorted_cache.pop(project_id, None)
        self.vectordb_client.create_collection(
            collection_name=collection_name,
            embedding_size=self.embedding_client.embedding_size,
            do_reset=do_reset,)
        contextual_retrieval_enabled = getattr(
            self.app_settings, "CONTEXTUAL_RETRIEVAL_ENABLED", False)
        cr_max_tokens = getattr(
            self.app_settings, "CONTEXTUAL_RETRIEVAL_MAX_TOKENS", 100)
        to_embed = []
        hits = 0
        misses = 0
        for chunk in chunks:
            doc_title = (chunk.metadata.get("doc_title")
                or chunk.metadata.get("source")
                or "Unknown document")
            page = chunk.metadata.get("page", "")
            section = (chunk.metadata.get("section_heading")
                or chunk.metadata.get("section")
                or "")
            chunk_type = chunk.metadata.get("chunk_type", "text")
            alt_text = (chunk.metadata.get("alt_text")
                or chunk.metadata.get("caption")
                or "")
            if chunk_type == "image" and not chunk.text.strip():
                proxy = (f"Figure from {doc_title}, page {page}, section '{section}'. "
                    f"{alt_text}").strip()
            elif chunk_type == "equation" and not chunk.text.strip():
                proxy = (
                    f"Mathematical equation from {doc_title}, page {page}, "
                    f"section '{section}'. {alt_text}"
                ).strip()
            else:
                proxy = chunk.text
            if contextual_retrieval_enabled:
                context_desc = None
                if self.contextual_cache is not None:
                    context_desc = self.contextual_cache.get(
                        doc_title=doc_title,
                        section=section,
                        chunk_text=proxy,)
                    if context_desc:
                        hits += 1
                #bt3ml brief about the chunk to help in retrieval
                if context_desc is None:
                    misses += 1
                    context_desc = _contextual_desc_call(
                        self.generation_client, doc_title, page, section, proxy, cr_max_tokens
                    )
                    if context_desc and self.contextual_cache is not None:
                        self.contextual_cache.set(
                            doc_title=doc_title, section=section,
                            chunk_text=proxy, description=context_desc.strip(),)

                if context_desc:
                    ctx_text = (f"{context_desc.strip()}\n\n"
                        f"Document: {doc_title} | Page: {page} | Section: {section}\n\n"
                        f"{proxy}")
                else:
                    ctx_text = (f"Document: {doc_title} | Page: {page} | Section: {section}\n\n"
                        f"{proxy}")
            else:
                ctx_text = (f"Document: {doc_title} | Page: {page} | Section: {section}\n\n"
                    f"{proxy}")
            to_embed.append(ctx_text)
        if contextual_retrieval_enabled and self.contextual_cache is not None:
            self.contextual_cache.flush()
            self.logger.info(f"contextual cache: {hits} hits, {misses} misses "
                f"(cache size: {self.contextual_cache.size()})")
        embeddings = [
            self.embedding_client.embed_text(text=t,
                document_type=DocumentTypeEnum.DOCUMENT.value,)
            for t in to_embed]
        record_ids = [c.chunk_id for c in chunks]
        success = self.vectordb_client.insert_many(
            collection_name=collection_name,
            texts=to_embed,
            vectors=embeddings,
            metadata=[c.metadata for c in chunks],
            record_ids=record_ids,)
        if not success:
            return 0
        if self.bm25_client is not None and self.app_settings.BM25_ENABLED:
            payloads = [
                {"text": to_embed[i], **(chunks[i].metadata or {})}
                for i in range(len(chunks))]
            if do_reset:
                self.bm25_client.delete_index(project_id)
            self.bm25_client.build_index(
                project_id=project_id,
                texts=to_embed,
                ids=record_ids,
                payloads=payloads,)
        self._build_chunk_caches(project_id, chunks=chunks)
        return len(chunks)
