# prompt engineering part for the rag system (takes retrieved chunks and returns the answer of the LLM)
import re
import time

from controllers._llm_calls import _strict_answer, _normal_answer

# catches common texts added to answer by LLM
_DISCLAIMER_PATTERNS = [
    re.compile(
        r"\s*\(?\s*Note:\s*[Tt]his (?:answer|response)\s+"
        r"(?:is not|did not come|does not come|was not)\s+"
        r"(?:from|based on)[^.)\n]*?(?:materials?|sources?|context)[^.)\n]*?\)?\.?\s*$",
        re.IGNORECASE,),
    re.compile(
        r"\s*\(?\s*Note:\s*[^)\n]*?(?:uploaded|study)\s+materials?[^)\n]*?\)?\.?\s*$",
        re.IGNORECASE,),
    re.compile(
        r"\s*\(?\s*Disclaimer:\s*[^)\n]*?materials?[^)\n]*?\)?\.?\s*$",
        re.IGNORECASE,),]


# uses previous _DISCLAIMER_PATTERNS to remove this extra text
def _strip_source_disclaimers(text: str) -> str:
    # make sure the input is string if not return it as it is
    if not isinstance(text, str):
        return text
    out = text
    for _ in range(3):
        changed = False
        for pat in _DISCLAIMER_PATTERNS:
            new = pat.sub("", out)
            if new != out:
                out = new
                changed = True
        if not changed:
            break
    return out.rstrip()

# catch source tags (i made the llm generate it but sometimes hallucinate and write many)
_SOURCE_TAG_RE = re.compile(r"\[Source\s+([\d,\s&and]+)\]", re.IGNORECASE)

def _drop_invalid_source_tags(text: str, num_sources: int) -> str:
    if not isinstance(text, str) or num_sources <= 0:
        return text

    def _clean(match: re.Match) -> str:
        nums_raw = match.group(1)
        nums = [int(n) for n in re.findall(r"\d+", nums_raw)]
        valid = [n for n in nums if 1 <= n <= num_sources]
        if not valid:
            return ""  # drop entirely — nothing to cite
        return "[source " + ", ".join(str(n) for n in valid) + "]"

    cleaned = _SOURCE_TAG_RE.sub(_clean, text)
    #collapse whitespace introduced by removed tags.
    cleaned = re.sub(r"[ \t]+([.,;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned

class _NLPGenerationMixin:
    # start getting answer after designing system prompt
    def generate_answer_from_sources(self,question: str,filtered_results: list,timings: dict,chat_history: list = None,) -> str:
        context_parts = []
        for i, result in enumerate(filtered_results, 1):
            payload = result["payload"]
            text = payload.get("text", "")
            score = result["score"]
            chunk_type = payload.get("chunk_type", "text")
            page = payload.get("page", "?")
            header = f"source {i} (relevance: {score:.2f}, page {page})"
            if chunk_type == "image":
                folded = result.get("caption_neighbors_folded", 0)
                extra = (
                    f" The body of this source contains BOTH the visual "
                    f"description AND the surrounding paragraph from the book."
                    if folded else ""
                )
                header += (
                    f"\n[IMAGE CHUNK — a figure on page {page}.{extra} "
                    f"You MUST describe what the figure shows AND explain how it "
                    f"illustrates the concept the student is asking about.]"
                )
            elif chunk_type == "equation":
                header += "\n[EQUATION CHUNK: a mathematical expression from the document]"
            elif chunk_type == "table":
                header += "\n[TABLE CHUNK: a data table from the document]"

            context_parts.append(f"{header}\n{text}")
        context = "\n\n".join(context_parts)

        strict = bool(getattr(self.app_settings, "STRICT_GROUNDING", False))
        if strict:
            answer = _strict_answer(self.generation_client, question, context, timings)
            if not answer or not answer.strip():
                return ("I wasn't able to generate an answer right now — the language model "
                    "returned an empty response. Please try again in a few seconds.")
            return _drop_invalid_source_tags(answer, num_sources=len(filtered_results))

        prior_turns = []
        if chat_history:
            for msg in chat_history[-6:]:
                role = msg.get("role", "")
                content = (msg.get("content") or "")[:800]
                if role in ("user", "assistant") and content:
                    prior_turns.append({"role": role, "content": content})

        answer = _normal_answer(self.generation_client, question, context, prior_turns, timings)

        if not answer or not answer.strip():
            return (
                "I wasn't able to generate an answer right now — the language model "
                "returned an empty response. This is usually a temporary rate-limit or "
                "API issue. Please try again in a few seconds."
            )

        answer = _strip_source_disclaimers(answer)
        answer = _drop_invalid_source_tags(answer, num_sources=len(filtered_results))
        return answer
