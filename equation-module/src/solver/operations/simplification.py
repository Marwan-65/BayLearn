"""Expression simplification handlers."""

import sympy as sp

from ...formatting import format_sympy_as_plain_text
from ...models.requests import SolverRequest
from ...utils.sympy_utils import parse_sympy_expression


def simplify_algebraic_expression(request: SolverRequest) -> str:
    """Simplify symbolic expression with pedagogical steps."""
    try:
        expression = parse_sympy_expression(request.equations[0].lhs)
        result = sp.simplify(expression)
        steps = [
            "Step 1: Original Expression",
            f"  {format_sympy_as_plain_text(expression)}",
            "\nStep 2: Apply Simplification",
            "  Using algebraic rules, trigonometric identities, and factoring",
            "\nStep 3: Simplified Result",
            f"  {format_sympy_as_plain_text(result)}",
        ]
        return f"{chr(10).join(steps)}\n\nFinal Result: {format_sympy_as_plain_text(result)}"
    except (TypeError, ValueError) as exc:
        return f"Error simplifying expression: {exc}"
