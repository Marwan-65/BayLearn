from pydantic import BaseModel, Field
from typing import List, Optional

# ── Difficulty Levels ─────────────────────────────────────────────────
"""
Difficulty Levels:
1. Easy - Recall facts, definitions, and basic concepts
2. Medium - Explain ideas, concepts, and apply knowledge
3. Hard - Analyze, evaluate, and create original solutions
"""

# ── What the caller sends to your API ──────────────────────────────────────
class GenerateQuestionsRequest(BaseModel):
    project_id: str = Field(..., description="The ID of the indexed project/document")
    topic: Optional[str] = Field(None, description="Optional: focus questions on a topic")
    difficulty: str = Field(default="medium", description="easy | medium | hard")
    question_type: str = Field(default="mcq", description="mcq | short_answer | true_false")

# ── One generated question ─────────────────────────────────────────────────
class QuestionOption(BaseModel):
    label: str          # "A", "B", "C", "D"
    text: str           # "The speed of light"
    is_correct: bool    # True for the correct answer

class GeneratedQuestion(BaseModel):
    question_text: str
    question_type: str  # "mcq", "short_answer", "true_false"
    options: Optional[List[QuestionOption]] = None   # Only for MCQ
    correct_answer: str                              # The answer text
    keywords_to_match: Optional[List[str]] = None    # Short-answer grading hints
    explanation: str                                 # Why this is correct
    source_chunk_id: Optional[int] = None           # Which chunk this came from
    difficulty: str
    validation_report: Optional[dict] = None        # Semantic validation result
    # ICL/classifier metadata — populated when BloomBERT weights are present.
    # predicted_level is None when running without a trained classifier.
    predicted_level: Optional[str] = None            # easy | medium | hard | None
    level_confidence: Optional[float] = None         # softmax prob of predicted_level

# ── What your API returns ──────────────────────────────────────────────────
class GenerateQuestionsResponse(BaseModel):
    project_id: str
    topic: Optional[str]
    questions: List[GeneratedQuestion]
    total_generated: int
    chunks_used: int    # How many source chunks were used