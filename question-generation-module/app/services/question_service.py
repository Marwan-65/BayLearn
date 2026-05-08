import json
import logging
import random
from typing import List, Optional

from app.llm.groq_client import QuestionGenLLMClient
from app.services.chunk_fetcher import ChunkFetcher
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
        fetch relevant chunks from RAG module
            → build LLM prompt
                → call Groq
                    → parse JSON response
                        → return GeneratedQuestion list
    """

    def __init__(self, llm_client: QuestionGenLLMClient, chunk_fetcher: ChunkFetcher):
        self.llm_client = llm_client
        self.chunk_fetcher = chunk_fetcher

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
        # 1. Decide what to search for
        search_query = topic if topic else "key concepts definitions important principles"

        # 2. Fetch relevant chunks from the RAG module (fetch more to allow randomization)
        raw_chunks = await self.chunk_fetcher.fetch_relevant_chunks(
            project_id=project_id,
            query=search_query,
            limit=20,  # Fetch 20 instead of 10 to enable sampling
        )

        if not raw_chunks:
            raise ValueError(f"No indexed content found for project '{project_id}'. "
                             "Make sure the project has been uploaded and indexed first.")

        # 3. Randomly sample from the fetched chunks for diversity
        # Use at most 10 but pick randomly to avoid always using the same top ones
        sample_size = min(10, len(raw_chunks))
        selected_chunks = random.sample(raw_chunks, sample_size)

        # 4. Join chunk texts, but don't exceed the LLM context limit
        chunks_text = self._prepare_context(selected_chunks)

        # 5. Build prompt based on question type
        if question_type == "mcq":
            system_prompt, user_prompt = build_mcq_prompt(chunks_text, num_questions, difficulty)
        elif question_type == "short_answer":
            system_prompt, user_prompt = build_short_answer_prompt(chunks_text, num_questions, difficulty)
        elif question_type == "true_false":
            system_prompt, user_prompt = build_true_false_prompt(chunks_text, num_questions, difficulty)
        else:
            raise ValueError(f"Unknown question_type: {question_type}. Use mcq, short_answer, or true_false.")

        # 6. Call the LLM with higher temperature for diversity
        raw_response = self.llm_client.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.85,  # Increased from 0.7 for more variety
            max_tokens=min(900, 220 + (num_questions * 140)),
        )

        # 7. Parse the JSON the LLM returned
        questions = self._parse_llm_response(raw_response, question_type)

        return questions, len(selected_chunks)

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
                explanation=item.get("explanation", ""),
                difficulty=item.get("difficulty", "medium"),
            ))

        return questions