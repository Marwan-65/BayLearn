"""Typed request models for solver operations."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional


@dataclass(frozen=True)
class EquationData:
    """Represents one parsed equation side pair."""

    lhs: str
    rhs: str


@dataclass(frozen=True)
class SolverRequest:
    """Represents a normalized solver request from AI JSON."""

    operation: str
    equations: List[EquationData]
    target_variables: List[str]
    matrix_operation: Optional[str] = None
    extra_params: Dict[str, Any] = field(default_factory=dict)
    raw_data: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_ai_data(cls, ai_data: Mapping[str, Any]) -> "SolverRequest":
        """Create a typed request from raw AI translation data.

        Args:
            ai_data: Raw translator JSON dictionary.

        Returns:
            A normalized SolverRequest.
        """
        equations_raw = ai_data.get("equations", [])
        equations = [
            EquationData(lhs=str(eq.get("lhs", "")), rhs=str(eq.get("rhs", "")))
            for eq in equations_raw
            if isinstance(eq, Mapping)
        ]
        return cls(
            operation=str(ai_data.get("operation", "")),
            equations=equations,
            target_variables=[str(v) for v in ai_data.get("target_variables", [])],
            matrix_operation=(
                str(ai_data.get("matrix_operation"))
                if ai_data.get("matrix_operation") is not None
                else None
            ),
            extra_params=dict(ai_data.get("extra_params", {}) or {}),
            raw_data=dict(ai_data),
        )
