from pydantic import BaseModel, Field, field_validator
from typing import Optional, Any, List


class ModuleInitRequest(BaseModel):
    """Generic initialization payload — each module defines its own fields."""
    config: dict = {}


class ModuleRunRequest(BaseModel):
    """Generic run payload — each module defines its own input shape."""
    input_data: dict = {}


# ═════════════════════════════════════════════════════════════
# Phase 4: Typed request schemas matching teammate module APIs
# ═════════════════════════════════════════════════════════════

class EquationRunRequest(BaseModel):
    """
    Matches the equation module's SolveRequest schema.
    POST /run expects {"query": "solve 2x + 3 = 7"}
    """
    query: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="The equation or math query to solve",
    )

    @field_validator("query")
    @classmethod
    def sanitize_query(cls, v: str) -> str:
        """Phase 6: Basic sanitization — strip control characters."""
        return v.strip()


class AnimationRunRequest(BaseModel):
    """
    Animation module request schema.
    Will be refined once the animation teammate provides their API contract.
    """
    data_structure: str = Field(
        default="linked_list",
        description="Data structure to animate",
    )
    operation: Optional[str] = Field(
        default=None,
        description="Operation to animate (insert, delete, traverse, etc.)",
    )
    initial_values: Optional[List[Any]] = Field(
        default=None,
        description="Initial values for the data structure",
    )
    params: Optional[dict] = Field(
        default=None,
        description="Additional operation parameters",
    )

    @field_validator("data_structure")
    @classmethod
    def validate_data_structure(cls, v: str) -> str:
        allowed = {
            "linked_list", "binary_tree", "bst", "stack", "queue",
            "graph", "array", "heap", "hash_table",
        }
        v = v.strip().lower()
        if v not in allowed:
            # Don't reject, just pass through — teammate module will validate
            pass
        return v


# ═════════════════════════════════════════════════════════════
# Phase 5: Input parsing proxy schema
# ═════════════════════════════════════════════════════════════

class InputParsingResponse(BaseModel):
    """
    Expected response shape from the input parsing module's /upload endpoint.
    Used for validation in the adapter layer.
    """
    source_type: str
    title: Optional[str] = None
    sections: list = []
    total_chunks: int = 0
