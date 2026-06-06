from pydantic import BaseModel, Field
from typing import Dict, List, Optional

class pushRequest(BaseModel):
    do_reset: Optional[int] = 0
class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str
class searchRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    limit: Optional[int] = Field(default=5, ge=1, le=50)
    chat_history: Optional[List[ChatMessage]] = Field(default=[])
