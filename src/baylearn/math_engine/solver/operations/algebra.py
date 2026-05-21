"""Algebra operation handlers."""

import sympy as sp

from ...api.response_builder import build_operation_response
from ...formatting import final_text, format_steps, format_student_linear_steps
from ...models.requests import SolverRequest
from ..symbolic_solver import build_equations, build_target_variables


def solve_equation(request: SolverRequest) -> str:
    """Solve single equation or equation system.

    Args:
        request: Typed solver request.

    Returns:
        Formatted solver output.
    """
    sympy_equations = build_equations(request)
    target_vars = build_target_variables(request)
    solutions = sp.solve(sympy_equations, target_vars)
    step_text = format_student_linear_steps(sympy_equations, target_vars, solutions)
    if step_text is None:
        step_text = format_steps(request.operation, sympy_equations, target_vars, solutions)
    return build_operation_response(step_text, final_text(request.operation, solutions, target_vars))
