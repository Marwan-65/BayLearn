from pydantic import BaseModel, Field
from typing import List, Optional

#  What the caller sends to your API 
class GenerateQuestionsRequest(BaseModel):
    project_id: str = Field(..., description="The ID of the indexed project/document")
    topic: Optional[str] = Field(None, description="Optional: focus questions on a topic")
    num_questions: int = Field(default=5, ge=1, le=20, description="How many questions to generate")
    difficulty: str = Field(default="medium", description="easy | medium | hard")
    question_type: str = Field(default="mcq", description="mcq | short_answer | true_false")

#  One generated question 
class QuestionOption(BaseModel):
    label: str 
    text: str
    is_correct: bool

class GeneratedQuestion(BaseModel):
    question_text: str
    question_type: str  # "mcq", "true_false"
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

#  What  API returns 
class GenerateQuestionsResponse(BaseModel):
    project_id: str
    topic: Optional[str]
    questions: List[GeneratedQuestion]
    total_generated: int
    chunks_used: int    # How many source chunks were used


#  Answer checking 
class CheckAnswerRequest(BaseModel):
    question_type: str = Field(..., description="mcq | short_answer | true_false")
    user_answer: str = Field(..., description="What the student answered (label, 'true'/'false', or free text)")
    correct_answer: str = Field(default="", description="The expected answer text")
    keywords_to_match: Optional[List[str]] = Field(default=None, description="Short-answer grading hints")
    options: Optional[List[QuestionOption]] = Field(default=None, description="MCQ options (to grade by label)")
    session_id: Optional[str] = Field(default=None, description="If set, records the result for an adaptive session so the agent can read it")


#  Adaptive  quiz loop 
class AdaptiveConfigRequest(BaseModel):
    file_ids: str = Field(..., description="Comma-joined file id(s) the agent's questions are generated from")
    question_type: Optional[str] = Field(default="mcq", description="mcq | short_answer | true_false")

class AdaptiveGenerateRequest(BaseModel):
    topic: Optional[str] = Field(default=None, description="Concept/topic the agent chose")
    difficulty: str = Field(default="medium", description="Easy | Medium | Hard (case-insensitive)")
    question_type: Optional[str] = Field(default=None, description="Overrides the session default if set")

class CheckAnswerResponse(BaseModel):
    is_correct: bool
    method: str                        
    score: Optional[float] = None      
    correct_answer: str = ""