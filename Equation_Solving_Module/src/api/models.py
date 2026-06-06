from typing import List, Dict, Any, Optional

from pydantic import BaseModel, Field


class SolveRequest(BaseModel):
    query: str = Field(..., description="Mathematical query or equation to solve")

class GraphableFunction(BaseModel):
    name: str = Field(..., description="Function name (e.g., 'Original Function')")
    expression: str = Field(..., description="Mathematical expression")
    var: str = Field(..., description="Variable name")
    type: str = Field(..., description="Function type")
    analysis: Optional[Dict[str, Any]] = Field(default=None, description="Symbolic graph analysis")


class SolveResponse(BaseModel):
    success: bool = Field(..., description="Whether the operation succeeded")
    operation: str = Field(..., description="Type of operation performed")
    steps: List[str] = Field(default_factory=list, description="Step-by-step solution")
    final_result: str = Field(..., description="Final result string")
    graphable_functions: List[GraphableFunction] = Field(
        default_factory=list,
        description="Functions that can be graphed"
    )
    ai_translation: Dict[str, Any] = Field(
        default_factory=dict,
        
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="extra metadata (e.g., execution_time_ms)"
    )
