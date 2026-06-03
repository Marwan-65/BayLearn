"""Differential-equation operation handlers."""

import sympy as sp
from sympy.parsing.sympy_parser import parse_expr

from ...formatting import explain_differential_equation_steps
from ...models.requests import SolverRequest


def solve_ode(request: SolverRequest) -> str:
    """Solve ODEs with pedagogical explanation.

    Args:
        request: Typed solver request.

    Returns:
        Formatted text output.
    """
    dependent_var_name = request.target_variables[0]
    independent_var_name = "x"
    dependent_var = sp.Function(dependent_var_name)
    independent_var = sp.Symbol(independent_var_name)
    equation_data = request.equations[0]

    try:
        lhs_expr = parse_expr(
            str(equation_data.lhs),
            local_dict={
                "Derivative": lambda *args: sp.Derivative(*args),
                dependent_var_name: dependent_var,
                "x": independent_var,
            },
        )
        rhs_expr = parse_expr(
            str(equation_data.rhs),
            local_dict={
                "Derivative": lambda *args: sp.Derivative(*args),
                dependent_var_name: dependent_var,
                "x": independent_var,
            },
        )
    except (SyntaxError, TypeError, ValueError):
        try:
            lhs_str = str(equation_data.lhs).replace(dependent_var_name, f"{dependent_var_name}(x)")
            rhs_str = str(equation_data.rhs).replace(dependent_var_name, f"{dependent_var_name}(x)")
            lhs_expr = parse_expr(
                lhs_str,
                local_dict={"Derivative": sp.Derivative, dependent_var_name: dependent_var},
            )
            rhs_expr = parse_expr(
                rhs_str,
                local_dict={"Derivative": sp.Derivative, dependent_var_name: dependent_var},
            )
        except (SyntaxError, TypeError, ValueError) as exc:
            return f"Error parsing differential equation: {exc}"

    diff_eq = sp.Eq(lhs_expr, rhs_expr)
    try:
        solution = sp.dsolve(diff_eq, dependent_var(independent_var))
        step_text = explain_differential_equation_steps(diff_eq, solution, dependent_var_name)
        return f"{step_text}\n\nFinal Result: {solution}"
    except (TypeError, ValueError, NotImplementedError) as exc:
        return f"Error solving differential equation: {exc}"
