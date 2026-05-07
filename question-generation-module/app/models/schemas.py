from pydantic import BaseModel, Field
from typing import List, Optional

# ── What the caller sends to your API ──────────────────────────────────────
class GenerateQuestionsRequest(BaseModel):
    project_id: str = Field(..., description="The ID of the indexed project/document")
    topic: Optional[str] = Field(None, description="Optional: focus questions on a topic")
    num_questions: int = Field(default=5, ge=1, le=20, description="How many questions to generate")
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
    explanation: str                                 # Why this is correct
    source_chunk_id: Optional[int] = None           # Which chunk this came from
    difficulty: str

# ── What your API returns ──────────────────────────────────────────────────
class GenerateQuestionsResponse(BaseModel):
    project_id: str
    topic: Optional[str]
    questions: List[GeneratedQuestion]
    total_generated: int
    chunks_used: int    # How many source chunks were used