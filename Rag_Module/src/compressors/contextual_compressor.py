
import re
import logging
from math import ceil
import numpy as np
from stores.LLM.LLMEnums import DocumentTypeEnum
logger = logging.getLogger(__name__)
# mainly we do not compress short chunks to not lose any info from them 
class AdaptiveContextualCompressor:
    def __init__(self,embedding_client,similarity_threshold: float = 0.3,min_chunk_length: int = 200,
        min_keep_ratio: float = 0.4,
        skip_single_chunk: bool = True,
    ):
        self.embedding_client = embedding_client
        self.similarity_threshold = similarity_threshold
        self.min_chunk_length = min_chunk_length
        self.min_keep_ratio = min_keep_ratio
        self.skip_single_chunk = skip_single_chunk

    def compress(self, chunks: list, query_embedding: list) -> list:
        if not chunks:
            return []

        if self.skip_single_chunk and len(chunks) == 1:
            chunks[0]["original_text"] = chunks[0]["text"]
            chunks[0]["compression_ratio"] = 1.0
            logger.info("single chunk retrieved so we skip compression")
            return chunks

        # check if all chunks are short
        all_short = all(
            len(c["text"]) < self.min_chunk_length for c in chunks
        )
        if len(chunks) <= 2 and all_short:
            for c in chunks:
                c["original_text"] = c["text"]
                c["compression_ratio"] = 1.0
            logger.info("all chunks are short so we skip compression")
            return chunks

        query_vec = np.array(query_embedding)
        # kol chunk we save original for debugging and evaluation
        for chunk in chunks:
            original_text = chunk["text"]
            chunk["original_text"] = original_text
            if len(original_text) < self.min_chunk_length:
                chunk["compression_ratio"] = 1.0
                continue
            # divide the chunk into sentences
            sentences = self._split_into_sentences(original_text)
            if len(sentences) <= 2:
                chunk["compression_ratio"] = 1.0
                continue
            # batch embed sentences
            sentence_embeddings = self.embedding_client.embed_texts_batch(
                sentences, DocumentTypeEnum.DOCUMENT.value
            )
            if not sentence_embeddings:
                chunk["compression_ratio"] = 1.0
                continue

            # measure cosine similarity between each sentence and query(question)
            similarities = [
                self._cosine_similarity(query_vec, np.array(se))
                for se in sentence_embeddings
            ]
            # similaity determines which sentences to keep
            min_keep_count = max(1, ceil(len(sentences) * self.min_keep_ratio))
            above_threshold = [
                (i, sim) for i, sim in enumerate(similarities)
                if sim >= self.similarity_threshold
            ]
            if len(above_threshold) >= min_keep_count:
                keep_indices = {i for i, _ in above_threshold}
            else:
                # not enough pass threshold so keep top-N by similarity
                # but sort as original order to keep flow of context
                sorted_by_sim = sorted(
                    enumerate(similarities), key=lambda x: x[1], reverse=True
                )
                keep_indices = {i for i, _ in sorted_by_sim[:min_keep_count]}
            compressed_sentences = [
                sentences[i] for i in sorted(keep_indices)
            ]
            compressed_text = " ".join(compressed_sentences)
            if not compressed_text.strip():
                compressed_text = original_text

            chunk["text"] = compressed_text
            chunk["compression_ratio"] = len(compressed_text) / max(len(original_text), 1)

            logger.info(
                f"compressed chunk: {len(original_text)} -> {len(compressed_text)} chars "
                f"(ratio: {chunk['compression_ratio']:.2f}, " # for testing
                f"kept {len(keep_indices)}/{len(sentences)} sentences)"
            )

        return chunks

    def _split_into_sentences(self, text: str) -> list:
        lines = text.split('\n')
        sentences = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # split on sentence-ending punctuation followed by space + uppercase
            parts = re.split(r'(?<=[.!?])\s+(?=[A-Z])', line)
            for part in parts:
                part = part.strip()
                if part:
                    sentences.append(part)
        return sentences
    @staticmethod
    def _cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        dot = np.dot(vec_a, vec_b)
        norm_a = np.linalg.norm(vec_a)
        norm_b = np.linalg.norm(vec_b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(dot / (norm_a * norm_b))
