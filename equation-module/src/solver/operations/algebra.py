import sympy as sp
from ...api.response_builder import build_operation_response
from ...formatting import format_final_math_answer, explain_general_math_steps, explain_linear_equation_steps
from ...models.requests import SolverRequest
from ..symbolic_solver import build_equations, build_target_variables


def solve_algebraic_equation(request: SolverRequest) -> str:
    """Solve single equation or equation system.
    Args:
        request: Typed solver request.
    Returns:
        Formatted solver output.
    """
    sympy_equations = build_equations(request)
    target_vars = build_target_variables(request)
    solutions = sp.solve(sympy_equations, target_vars)
    step_text = explain_linear_equation_steps(sympy_equations, target_vars, solutions)
    if step_text is None:
        step_text = explain_general_math_steps(request.operation, sympy_equations, target_vars, solutions)
    return build_operation_response(step_text, format_final_math_answer(request.operation, solutions, target_vars))
