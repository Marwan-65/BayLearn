from typing import Any, List

from .expression_formatter import format_sympy_as_plain_text
from .latex_utils import convert_to_safe_latex


def format_final_math_answer(operation: str, result: Any, target_vars: List[Any]) -> str:
    # format single mathematical operations with latex
    if operation in ["derive", "integrate", "simplify", "partial_derivative", "limit", "series"]:
        return f"${convert_to_safe_latex(result)}$"

    # cast matrix operations directly to string
    if operation in ["matrix_ops"]:
        return str(result)

    # format dictionary results as equations
    if isinstance(result, dict):
        return ", ".join(f"${v} = {convert_to_safe_latex(result[v])}$" for v in target_vars if v in result)

    # format list of single variable solutions
    if isinstance(result, list) and len(target_vars) == 1:
        v = target_vars[0]
        return " | ".join(f"Solution {i}: ${v} = {convert_to_safe_latex(val)}$" for i, val in enumerate(result, 1))

    # format list of tuple solutions for multiple variables
    if isinstance(result, list) and result and isinstance(result[0], tuple):
        solution_parts = []
        for solution_index, values in enumerate(result, start=1):
            assignments = []
            for var_index, value in enumerate(values):
                if var_index < len(target_vars):
                    assignments.append(f"${target_vars[var_index]} = {convert_to_safe_latex(value)}$")
            solution_parts.append(f"Solution {solution_index}: {', '.join(assignments)}")
        return " | ".join(solution_parts)

    return format_sympy_as_plain_text(result)