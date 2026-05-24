import json
import logging
from typing import List, Optional

from app.llm.groq_client import QuestionGenLLMClient
from app.services.chunk_fetcher import ChunkFetcher
from app.services.context_enrichment import ContextEnrichmentLayer
from app.services.semantic_validator import SemanticValidator
from app.services.prompt_builder import (
    build_mcq_prompt,
    build_short_answer_prompt,
    build_true_false_prompt,
)
from app.models.schemas import GeneratedQuestion, QuestionOption

logger = logging.getLogger(__name__)

# Max characters of chunk text to include in a single prompt.
# Keep this conservative to avoid Groq on-demand TPM 413 errors.
MAX_CONTEXT_CHARS = 2200

# Prevent one large chunk from consuming the whole prompt budget.
MAX_SINGLE_CHUNK_CHARS = 700


class QuestionGenerationService:
    """
    Core service for generating quiz questions from study material.

    Flow:
        Context Enrichment Layer (multi-query + MMR selection)
            → build LLM prompt
                → call Groq
                    → parse JSON response
                        → return GeneratedQuestion list
    """

    def __init__(self, llm_client: QuestionGenLLMClient, chunk_fetcher: ChunkFetcher):
        self.llm_client = llm_client
        self.chunk_fetcher = chunk_fetcher
        self.context_enricher = ContextEnrichmentLayer(chunk_fetcher)
        self.validator = SemanticValidator()

    async def generate(
        self,
        project_id: str,
        num_questions: int,
        difficulty: str,
        question_type: str,
        topic: Optional[str] = None,
    ) -> tuple[List[GeneratedQuestion], int]:
        """
        Generate questions for a project.

        Returns: (list of GeneratedQuestion, number_of_chunks_used)
        """
        # 1. Context Enrichment Layer:
        #    Fire multiple difficulty-aware queries to the RAG module,
        #    deduplicate results, then use MMR to select chunks that are
        #    both relevant AND diverse (covers different concepts).
        selected_chunks, enrichment_diagnostics = await self.context_enricher.get_chunks(
            project_id=project_id,
            difficulty=difficulty,
            topic=topic,
            n=10,
        )

        if not selected_chunks:
            raise ValueError(f"No indexed content found for project '{project_id}'. "
                             "Make sure the project has been uploaded and indexed first.")

        logger.info(
            "Enrichment diagnostics | difficulty=%s queries=%d retrieved=%d unique=%d selected=%d avg_score=%.3f",
            enrichment_diagnostics["difficulty"],
            enrichment_diagnostics["queries_fired"],
            enrichment_diagnostics["total_retrieved"],
            enrichment_diagnostics["unique_after_dedup"],
            enrichment_diagnostics["selected_by_mmr"],
            enrichment_diagnostics["avg_relevance_score"],
        )

        # 2. Join chunk texts, but don't exceed the LLM context limit
        chunks_text = self._prepare_context(selected_chunks)

        # 3. Build prompt based on question type
        if question_type == "mcq":
            system_prompt, user_prompt = build_mcq_prompt(chunks_text, num_questions, difficulty)
        elif question_type == "short_answer":
            system_prompt, user_prompt = build_short_answer_prompt(chunks_text, num_questions, difficulty)
        elif question_type == "true_false":
            system_prompt, user_prompt = build_true_false_prompt(chunks_text, num_questions, difficulty)
        else:
            raise ValueError(f"Unknown question_type: {question_type}. Use mcq, short_answer, or true_false.")

        # 4. Call the LLM
        raw_response = self.llm_client.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.85,  # Increased from 0.7 for more variety
            max_tokens=min(900, 220 + (num_questions * 140)),
        )

        # 5. Parse the JSON the LLM returned
        questions = self._parse_llm_response(raw_response, question_type)

        # 6. Semantic Validation Layer:
        #    Run all five validators against the source chunks.
        #    Rejected questions are dropped; flagged questions are kept but
        #    their validation_report is attached for the caller to inspect.
        chunk_texts = [
            c.get("payload", {}).get("text", "")
            for c in selected_chunks
            if c.get("payload", {}).get("text")
        ]
        reports = self.validator.validate_all(questions, chunk_texts)

        validated_questions: List[GeneratedQuestion] = []
        for question, report in zip(questions, reports):
            if report.decision == "reject":
                logger.warning(
                    "Question REJECTED by semantic validator: '%s…' | failures: %s",
                    question.question_text[:60],
                    [r.detail for r in report.results if not r.passed],
                )
                continue
            # Attach the compact validation report to the question object
            question.validation_report = report.to_dict()
            validated_questions.append(question)

        logger.info(
            "Validation summary: %d/%d questions passed (rejected=%d)",
            len(validated_questions), len(questions),
            len(questions) - len(validated_questions),
        )

        return validated_questions, len(selected_chunks)

    def _prepare_context(self, raw_chunks: list) -> str:
        """
        Join chunk texts into a single string for the prompt.
        Truncate to MAX_CONTEXT_CHARS to avoid hitting LLM limits.
        """
        parts = []
        total_chars = 0

        for chunk in raw_chunks:
            text = chunk.get("payload", {}).get("text", "")
            if not text:
                continue
            text = text[:MAX_SINGLE_CHUNK_CHARS]
            if total_chars + len(text) > MAX_CONTEXT_CHARS:
                # Add a partial chunk so we don't waste space
                remaining = MAX_CONTEXT_CHARS - total_chars
                parts.append(text[:remaining])
                break
            parts.append(text)
            total_chars += len(text)

        return "\n\n---\n\n".join(parts)

    def _parse_llm_response(self, raw_response: str, question_type: str) -> List[GeneratedQuestion]:
        """
        Parse the JSON array the LLM returned into GeneratedQuestion objects.

        The LLM sometimes wraps JSON in markdown code fences like ```json ... ```
        This method handles that gracefully.
        """
        # Strip markdown code fences if present
        text = raw_response.strip()
        if text.startswith("```"):
            # Remove first line (```json or ```) and last line (```)
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"LLM returned invalid JSON: {e}\nRaw response: {raw_response[:500]}")
            raise ValueError("The LLM returned malformed JSON. Try again.")

        questions = []
        for item in data:
            # Build options list only for MCQ
            options = None
            if question_type == "mcq" and "options" in item:
                options = [
                    QuestionOption(
                        label=opt["label"],
                        text=opt["text"],
                        is_correct=opt.get("is_correct", False),
                    )
                    for opt in item.get("options", [])
                ]

            questions.append(GeneratedQuestion(
                question_text=item.get("question_text", ""),
                question_type=question_type,
                options=options,
                correct_answer=item.get("correct_answer", ""),
                keywords_to_match=self._extract_keywords(item.get("keywords_to_match")),
                explanation=item.get("explanation", ""),
                difficulty=item.get("difficulty", "medium"),
            ))

        return questions

    def _extract_keywords(self, raw_keywords: object) -> Optional[List[str]]:
        """
        Normalize keyword hints returned by the LLM.

        Accepts list input and removes empty/duplicate values.
        """
        if not isinstance(raw_keywords, list):
            return None

        seen = set()
        cleaned: List[str] = []
        for item in raw_keywords:
            if not isinstance(item, str):
                continue
            kw = item.strip().lower()
            if not kw or kw in seen:
                continue
            seen.add(kw)
            cleaned.append(kw)

        return cleaned or None