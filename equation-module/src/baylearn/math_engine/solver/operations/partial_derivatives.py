"""Partial-derivative operation handlers."""

import sympy as sp

from ...formatting import expr_text, format_partial_derivative_steps
from ...models.requests import SolverRequest
from ...utils.sympy_utils import parse_sympy_expression


def compute_partial_derivative(request: SolverRequest) -> str:
    """Compute mixed partial derivatives in requested order."""
    try:
        expression = parse_sympy_expression(request.equations[0].lhs)
        variables = [sp.Symbol(var) for var in request.target_variables]
        result = expression
        for var in variables:
            result = sp.diff(result, var)
        step_text = format_partial_derivative_steps(expression, variables, result)
        return f"{step_text}\n\nFinal Result: {expr_text(result)}"
    except (TypeError, ValueError) as exc:
        return f"Error computing partial derivative: {exc}"
