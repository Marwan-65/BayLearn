"""Limit operation handlers."""

import sympy as sp

from ...formatting import format_sympy_as_plain_text, explain_limit_evaluation_steps
from ...models.requests import SolverRequest
from ...utils.sympy_utils import parse_sympy_expression


def evaluate_limit(request: SolverRequest) -> str:
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
        step_text = explain_limit_evaluation_steps(expression, variable, approach_value, direction, result)
        return f"{step_text}\n\nFinal Result: {format_sympy_as_plain_text(result)}"
    except (TypeError, ValueError, NotImplementedError) as exc:
        return f"Error calculating limit: {exc}"
