"""Pydantic models for FastAPI endpoints."""

from typing import List, Dict, Any

from pydantic import BaseModel, Field


class SolveRequest(BaseModel):
    """Request body for solve endpoint."""
    query: str = Field(..., description="Mathematical query or equation to solve")


class GraphableFunction(BaseModel):
    """Representation of a graphable function."""
    name: str = Field(..., description="Function name (e.g., 'Original Function')")
    expression: str = Field(..., description="Mathematical expression")
    var: str = Field(..., description="Variable name")
    type: str = Field(..., description="Function type (e.g., 'original', 'derivative')")


class SolveResponse(BaseModel):
    """Response body for solve endpoint."""
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
        description="AI translation of the input"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (e.g., execution_time_ms)"
    )
