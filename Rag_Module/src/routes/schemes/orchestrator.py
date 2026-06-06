from pydantic import BaseModel, Field, field_validator
from typing import Optional, Any

class ModuleInitRequest(BaseModel):
    config: dict = {}
class ModuleRunRequest(BaseModel):
    input_data: dict = {}

class EquationRunRequest(BaseModel):
    query: str = Field(...,min_length=1,max_length=5000,
        description="The equation or math query to solve",)

    @field_validator("query")
    @classmethod
    def sanitize_query(cls, v: str) -> str:
        return v.strip()

class InputParsingResponse(BaseModel):
    file_id: Optional[str] = None   
    source_type: str
    title: Optional[str] = None
    sections: list = []
    total_chunks: int = 0