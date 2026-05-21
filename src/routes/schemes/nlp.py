from pydantic import BaseModel, Field
from typing import Optional


class pushRequest(BaseModel):
    do_reset: Optional[int] = 0


class searchRequest(BaseModel):
    # Pydantic enforces length at request-validation time, returning a 422
    # with a clear error message if a client sends an oversized question.
    # This is the first line of defense against prompt-injection payload
    # floods and LLM token-budget abuse.
    text: str = Field(..., min_length=1, max_length=5000)
    limit: Optional[int] = Field(default=5, ge=1, le=50)
