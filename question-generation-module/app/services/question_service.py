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
from app.classifier.bloom_classifier import BloomClassifier, bloom6_to_level
from app.services.example_bank import ExampleBank

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

    def __init__(self, llm_client: QuestionGenLLMClient, chunk_fetcher: ChunkFetcher,
                 example_bank: Optional[ExampleBank] = None,
                 bloom_classifier: Optional[BloomClassifier] = None,
                 few_shot_k: int = 10,
                 retry_on_level_mismatch: bool = True):
        self.llm_client = llm_client
        self.chunk_fetcher = chunk_fetcher
        self.context_enricher = ContextEnrichmentLayer(chunk_fetcher)
        self.validator = SemanticValidator()
        self.example_bank = example_bank
        self.bloom_classifier = bloom_classifier
        self.few_shot_k = few_shot_k
        self.retry_on_level_mismatch = retry_on_level_mismatch

    async def generate(
        self,
        project_id: str,
        num_questions: int,
        difficulty: str,
        question_type: str,
        topic: Optional[str] = None,
        include_guidance: bool = True,
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

        # 5. ICL: retrieve few-shot examples by cosine similarity to the
        #    chunk/topic, level-filtered. The bank no longer uses subject
        #    filtering — concept matching is fully delegated to the embedding
        #    similarity (the query encodes the concept directly).
        target_level = bloom6_to_level(difficulty)  # 6-level → easy/medium/hard
        # Query with topic + source context (not the bare topic word) so the
        # embedder disambiguates homonyms — e.g. OS "threads" vs mechanical
        # "thread cutting" — by grounding the match in the actual chunk text.
        few_shot_query = f"{topic}. {chunks_text[:500]}" if topic else chunks_text[:600]
        few_shot = self._retrieve_few_shot(
            query_text=few_shot_query,
            target_level=target_level,
        )
        logger.info(
            "ICL: %d examples retrieved (target_level=%s)",
            len(few_shot), target_level,
        )

        # 6. Build prompt, call LLM, parse — possibly retry once on level mismatch
        questions = await self._generate_with_retry(
            question_type=question_type,
            chunks_text=chunks_text,
            num_questions=num_questions,
            difficulty=difficulty,
            target_level=target_level,
            few_shot=few_shot,
            include_guidance=include_guidance,
        )

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

    # helpers
    def _retrieve_few_shot(self, query_text: str, target_level: str) -> list:
        if not self.example_bank or not self.example_bank.entries:
            return []
        try:
            return self.example_bank.retrieve(
                query_text=query_text, target_level=target_level,
                k=self.few_shot_k,
            )
        except Exception as e:  # never fail generation due to ICL 
            logger.warning("Few-shot retrieval failed: %s — proceeding without ICL", e)
            return []

    def _build_prompt(self, question_type, chunks_text, num_questions,
                      difficulty, few_shot, include_guidance=True):
        if question_type == "mcq":
            return build_mcq_prompt(chunks_text, num_questions, difficulty, few_shot, include_guidance)
        if question_type == "short_answer":
            return build_short_answer_prompt(chunks_text, num_questions, difficulty, few_shot, include_guidance)
        if question_type == "true_false":
            return build_true_false_prompt(chunks_text, num_questions, difficulty, few_shot, include_guidance)
        raise ValueError(f"Unknown question_type: {question_type}. Use mcq, short_answer, or true_false.")

    async def _generate_with_retry(self, question_type, chunks_text,
                                   num_questions, difficulty, target_level,
                                   few_shot, include_guidance=True) -> List[GeneratedQuestion]:
        """Generate, classify output, retry once if too many wrong-level questions."""
        attempts = 0
        max_attempts = 2 if self.retry_on_level_mismatch else 1
        last_questions: List[GeneratedQuestion] = []

        while attempts < max_attempts:
            attempts += 1
            system_prompt, user_prompt = self._build_prompt(
                question_type, chunks_text, num_questions, difficulty, few_shot,
                include_guidance=include_guidance,
            )
            raw_response = self.llm_client.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                # Slightly lower temperature on retry to converge on correct level
                temperature=0.85 if attempts == 1 else 0.6,
                max_tokens=2048,
            )
            questions = self._parse_llm_response(raw_response, question_type)
            last_questions = self._classify_predicted_levels(questions)

            # Decide if we need a retry
            if not self.bloom_classifier or attempts == max_attempts:
                break
            mismatches = sum(
                1 for q in last_questions
                if q.predicted_level and q.predicted_level != target_level
            )
            if mismatches <= len(last_questions) // 2:
                break  # majority correct -> accept , to overcome classifier noise
            logger.info(
                "ICL retry: %d/%d questions had wrong level on attempt %d "
                "(target=%s). Retrying with lower temperature.",
                mismatches, len(last_questions), attempts, target_level,
            )

        return last_questions

    def _classify_predicted_levels(self, questions: List[GeneratedQuestion]) -> List[GeneratedQuestion]:
        """Annotate each question with predicted_level / confidence from BloomBERT."""
        if not self.bloom_classifier or not questions:
            return questions
        texts = [q.question_text for q in questions]
        preds = self.bloom_classifier.predict_batch(texts)
        for q, p in zip(questions, preds):
            q.predicted_level = p.level
            q.level_confidence = p.confidence
        return questions

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