# this for extracting equations from the retrieved chunks 
import json
from controllers._llm_calls import _equation_extract_call
class _NLPExtractionMixin:
    def extract_equation_from_sources(self, filtered_results: list, question: str) -> str:
        eq_chunks = [
            r for r in filtered_results
            if r["payload"].get("chunk_type") in ("equation", "table")
        ]
        if eq_chunks:
            return eq_chunks[0]["payload"].get("text", "")
        math_chunks = []
        for r in filtered_results:
            if self._has_math_content(r["payload"].get("text", "")):
                math_chunks.append(r)
        if math_chunks:
            return math_chunks[0]["payload"].get("text", "")

        src_txt = "\n\n".join(r["payload"].get("text", "") for r in filtered_results[:3])
        extracted = _equation_extract_call(self.generation_client, question, src_txt)
        if extracted:
            return extracted

        return question