"""Limit operation handlers."""

import sympy as sp

from ...formatting import expr_text, format_limit_steps
from ...models.requests import SolverRequest
from ...utils.sympy_utils import parse_sympy_expression


def compute_limit(request: SolverRequest) -> str:
    """Compute symbolic limit with optional one-sided direction."""
    try:
        expression = parse_sympy_expression(request.equations[0].lhs)
        variable = sp.Symbol(request.target_variables[0])
        approach_value = parse_sympy_expression(request.equations[0].rhs)
        direction = request.extra_params.get("direction", "+-")
        if direction == "+":
            result = sp.limit(expression, variable, approach_value, "+")
        elif direction == "-":
            result = sp.limit(expression, variable, approach_value, "-")
        else:
            result = sp.limit(expression, variable, approach_value)
        step_text = format_limit_steps(expression, variable, approach_value, direction, result)
        return f"{step_text}\n\nFinal Result: {expr_text(result)}"
    except (TypeError, ValueError, NotImplementedError) as exc:
        return f"Error calculating limit: {exc}"
