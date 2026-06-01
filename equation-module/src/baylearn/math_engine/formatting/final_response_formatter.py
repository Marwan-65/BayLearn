"""Final user-facing response formatting."""

from typing import Any, List

from .expression_formatter import expr_text
from .latex_utils import safe_latex


def final_text(operation: str, result: Any, target_vars: List[Any]) -> str:
    """Format final result text by operation type.

    Args:
        operation: Operation name.
        result: Symbolic result.
        target_vars: SymPy target variables.

    Returns:
        Final formatted result text.
    """
    if operation in ["derive", "integrate", "simplify", "partial_derivative", "limit", "series"]:
        return f"${safe_latex(result)}$"

    if operation in ["matrix_ops"]:
        return str(result)

    if isinstance(result, dict):
        return ", ".join(f"${v} = {safe_latex(result[v])}$" for v in target_vars if v in result)

    if isinstance(result, list) and len(target_vars) == 1:
        v = target_vars[0]
        return " | ".join(f"Solution {i}: ${v} = {safe_latex(val)}$" for i, val in enumerate(result, 1))

    if isinstance(result, list) and result and isinstance(result[0], tuple):
        solution_parts = []
        for solution_index, values in enumerate(result, start=1):
            assignments = []
            for var_index, value in enumerate(values):
                if var_index < len(target_vars):
                    assignments.append(f"${target_vars[var_index]} = {safe_latex(value)}$")
            solution_parts.append(f"Solution {solution_index}: {', '.join(assignments)}")
        return " | ".join(solution_parts)

    return expr_text(result)
