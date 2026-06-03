"""Calculus operation handlers."""

import sympy as sp

from ...api.response_builder import build_operation_response
from ...formatting import format_final_math_answer, explain_general_math_steps, convert_to_safe_latex
from ...models.requests import SolverRequest
from ..symbolic_solver import build_equations, build_target_variables


def calculate_derivative(request: SolverRequest) -> str:
    """Compute derivative with educational explanation."""
    sympy_equations = build_equations(request)
    target_vars = build_target_variables(request)
    derivative = sp.diff(sympy_equations[0].lhs, target_vars[0])
    step_text = explain_general_math_steps(request.operation, sympy_equations, target_vars, derivative)
    final_result = format_final_math_answer(request.operation, derivative, target_vars)
    graphable_section = "\n\nGraphable Functions:"
    graphable_section += f"\n- Original: $y = {convert_to_safe_latex(sympy_equations[0].lhs)}$"
    graphable_section += f"\n- Derivative: $y = {convert_to_safe_latex(derivative)}$"
    return build_operation_response(step_text, f"\n{final_result}{graphable_section}")


def calculate_integral(request: SolverRequest) -> str:
    """Compute indefinite integral with educational explanation."""
    sympy_equations = build_equations(request)
    target_vars = build_target_variables(request)
    integral = sp.integrate(sympy_equations[0].lhs, target_vars[0])
    step_text = explain_general_math_steps(request.operation, sympy_equations, target_vars, integral)
    final_result = f"{format_final_math_answer(request.operation, integral, target_vars)} + C"
    graphable_section = "\n\nGraphable Functions:"
    graphable_section += f"\n- Original: $y = {convert_to_safe_latex(sympy_equations[0].lhs)}$"
    graphable_section += f"\n- Integral: $y = {convert_to_safe_latex(integral)} + C$"
    return build_operation_response(step_text, f"\n{final_result}{graphable_section}")
