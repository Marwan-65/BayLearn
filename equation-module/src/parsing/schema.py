from typing import Any, Dict, List, Optional, TypedDict

class EquationPayload(TypedDict):
    """Raw equation payload from LLM parser."""

    lhs: str
    rhs: str


class SolverPayload(TypedDict, total=False):
    """Raw solver payload produced by the LLM parser."""

    operation: str
    equations: List[EquationPayload]
    target_variables: List[str]
    matrix_operation: Optional[str]
    extra_params: Dict[str, Any]
