import json
import logging
from typing import List, Optional

from question_generation_model.llm.groq_client import QuestionGenLLMClient
from app.services.chunk_fetcher import ChunkFetcher
from app.services.context_enrichment import ContextEnrichmentLayer
from app.services.semantic_validator import SemanticValidator
from question_generation_model.prompt_builder import (
    build_mcq_prompt,
    build_short_answer_prompt,
    build_true_false_prompt,
)
from app.models.schemas import GeneratedQuestion, QuestionOption
from app.classifier.bloom_classifier import BloomClassifier, bloom6_to_level
from app.services.example_bank import ExampleBank

# this to make python to display INFO-level logs in the terminal
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

MAX_CONTEXT_CHARS = 6000
MAX_SINGLE_CHUNK_CHARS = 2000
MAX_REJECTION_RETRIES = 5


class QuestionGenerationService:
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

    async def generate(self,project_id: str,num_questions: int,        
        difficulty: str,question_type: str,topic: Optional[str] = None,
        include_guidance: bool = True,) -> tuple[List[GeneratedQuestion], int]:
        selected_chunks, enrichment_diagnostics = await self.context_enricher.get_chunks(
            project_id=project_id,difficulty=difficulty,
            topic=topic,n=10,)

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
        chunks_text = self._prepare_context(selected_chunks)
        target_level = bloom6_to_level(difficulty)  # 6-level → easy/medium/hard
        few_shot_query = f"{topic}. {chunks_text[:500]}" if topic else chunks_text[:600]
        few_shot = self._retrieve_few_shot(
            query_text=few_shot_query,
            target_level=target_level,
        )
        logger.info(
            "ICL: %d examples retrieved (target_level=%s)",
            len(few_shot), target_level,
        )
        questions = await self._generate_with_retry(
            question_type=question_type,
            chunks_text=chunks_text,
            num_questions=num_questions,
            difficulty=difficulty,
            target_level=target_level,
            few_shot=few_shot,
            include_guidance=include_guidance,
        )
        chunk_texts = [
            c.get("payload", {}).get("text", "")
            for c in selected_chunks
            if c.get("payload", {}).get("text")
        ]
        attempts = 0
        last_question: Optional[GeneratedQuestion] = None
        last_report = None

        while attempts < MAX_REJECTION_RETRIES:
            attempts += 1
            if attempts > 1:
                questions = await self._generate_with_retry(
                    question_type=question_type,
                    chunks_text=chunks_text,
                    num_questions=num_questions,
                    difficulty=difficulty,
                    target_level=target_level,
                    few_shot=few_shot,
                    include_guidance=include_guidance,)

            if not questions:
                logger.warning("Generation attempt %d returned no questions. Retrying.", attempts)
                continue

            question = questions[0]
            report = self.validator.validate_all([question], chunk_texts)[0]
            question.validation_report = report.to_dict()
            last_question = question
            last_report = report
            if report.decision != "reject":
                logger.info("Question accepted by validator on attempt %d.", attempts)
                return [question], len(selected_chunks)
            logger.warning(
                "Question REJECTED by semantic validator on attempt %d: '%s…' | failures: %s",
                attempts,
                question.question_text[:60],
                [r.detail for r in report.results if not r.passed],
            )
        if last_question is not None:
            fallback_report = last_report.to_dict() if last_report else {}
            fallback_report["forced_accept"] = True
            fallback_report["note"] = "Returned after max validation retries to avoid empty response."
            last_question.validation_report = fallback_report
            logger.warning(
                "Returning fallback question after %d rejected attempts to avoid empty response.",
                MAX_REJECTION_RETRIES,)
            return [last_question], len(selected_chunks)

        raise ValueError("Unable to generate a question after repeated retries.")

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
        qt = (question_type or "mcq").lower().strip()   
        if qt == "mcq":
            return build_mcq_prompt(chunks_text, num_questions, difficulty, few_shot, include_guidance)
        if qt == "short_answer":
            return build_short_answer_prompt(chunks_text, num_questions, difficulty, few_shot, include_guidance)
        if qt == "true_false":
            return build_true_false_prompt(chunks_text, num_questions, difficulty, few_shot, include_guidance)
        raise ValueError(f"Unknown question_type: {question_type}. Use mcq, short_answer, or true_false.")

    async def _generate_with_retry(self, question_type, chunks_text,
    num_questions, difficulty, target_level,
                few_shot, include_guidance=True) -> List[GeneratedQuestion]:
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
                # slightly lower temperature on retry to converge on correct level
                temperature=0.85 if attempts == 1 else 0.6,
                max_tokens=2048,
            )
            
            logger.info(f"\n RAW LLM response (attempt {attempts}) n{raw_response}\n")
            questions = self._parse_llm_response(raw_response, question_type)
            last_questions = self._classify_predicted_levels(questions)
            if not self.bloom_classifier or attempts == max_attempts:
                break
            if not last_questions:
                continue
            predicted_level = last_questions[0].predicted_level
            if predicted_level == target_level:
                break
            logger.info("ICL retry: wrong level on attempt %d (predicted=%s target=%s). "
                "Retrying with lower temperature.",
                attempts, predicted_level, target_level,)
        return last_questions

    def _classify_predicted_levels(self, questions: List[GeneratedQuestion]) -> List[GeneratedQuestion]:
        if not self.bloom_classifier or not questions:
            return questions
        texts = [q.question_text for q in questions]
        preds = self.bloom_classifier.predict_batch(texts)
        for q, p in zip(questions, preds):
            q.predicted_level = p.level
            q.level_confidence = p.confidence
        return questions

    def _prepare_context(self, raw_chunks: list) -> str:
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
        text = raw_response.strip()
        start_idx = text.find('[')
        end_idx = text.rfind(']')
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            text = text[start_idx:end_idx+1]

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"LLM returned invalid JSON: {e}\nRaw response: {raw_response[:500]}")
            raise ValueError("The LLM returned malformed JSON. Try again.")

        qtype = (question_type or "mcq").lower().strip()
        questions = []
        for item in data:
            # Build options list only for mcq
            # Default to an empty array instead of None to prevent React map() crashes
            options = [] if qtype == "mcq" else None
            if qtype == "mcq" and "options" in item:
                options = [
                    QuestionOption(
                        label=opt["label"],
                        text=opt["text"],
                        is_correct=opt.get("is_correct", False),
                    )
                    for opt in item.get("options", [])
                ]

            questions.append(GeneratedQuestion(
                question_text=item.get("question_text") or "",
                question_type=qtype,
                options=options,
                correct_answer=item.get("correct_answer") or "",
                keywords_to_match=self._extract_keywords(item.get("keywords_to_match")),
                explanation=item.get("explanation") or "",
                difficulty=item.get("difficulty") or "medium",))
        return questions

    def _extract_keywords(self, raw_keywords: object) -> Optional[List[str]]:
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
