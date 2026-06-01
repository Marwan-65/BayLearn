"""Graphable-function extraction from solver payloads."""

from typing import Any, Dict, List

import sympy as sp
from sympy.parsing.sympy_parser import parse_expr


def _as_symbol(name: Any) -> sp.Symbol:
    """Convert variable names from payload to SymPy symbols."""
    return sp.Symbol(str(name))


def _extract_system_graphs(ai_data: Dict[str, Any]) -> List[Dict[str, str]]:
    """Build graphable y(x)-style expressions from equation systems when possible."""
    graphable: List[Dict[str, str]] = []
    equations = ai_data.get("equations") or []
    target_variables = ai_data.get("target_variables") or []

    if len(target_variables) < 2:
        return graphable

    independent = _as_symbol(target_variables[0])
    dependent = _as_symbol(target_variables[1])

    for index, raw_equation in enumerate(equations, start=1):
        lhs_expr = parse_expr(str(raw_equation.get("lhs", "0")))
        rhs_expr = parse_expr(str(raw_equation.get("rhs", "0")))
        equation = sp.Eq(lhs_expr, rhs_expr)

        solved = sp.solve(equation, dependent)
        if not isinstance(solved, list):
            solved = [solved]

        for branch_index, branch in enumerate(solved, start=1):
            if branch is None:
                continue
            if not branch.free_symbols.issubset({independent}):
                continue
            suffix = f" (branch {branch_index})" if len(solved) > 1 else ""
            graphable.append(
                {
                    "name": f"Eq {index}{suffix}",
                    "expression": str(sp.simplify(branch)),
                    "var": str(independent),
                    "type": "system",
                }
            )

    return graphable


def extract_graphable_functions(
    operation: str, ai_data: Dict[str, Any], solver_output: str
) -> List[Dict[str, str]]:
    """Extract graphable functions from operation context.

    Args:
        operation: Operation key.
        ai_data: Raw translator payload.
        solver_output: Full solver output string.

    Returns:
        List of graphable function dictionaries.
    """
    del solver_output
    graphable: List[Dict[str, str]] = []
    try:
        if operation == "derive":
            original_expr = str(ai_data["equations"][0]["lhs"])
            var = ai_data["target_variables"][0]
            expr_obj = parse_expr(original_expr)
            derivative_obj = sp.diff(expr_obj, sp.Symbol(var))
            graphable.append(
                 {"name": "Original Function", "expression": str(expr_obj), "var": var, "type": "original"}
            )
            graphable.append(
                 {"name": "Derivative", "expression": str(derivative_obj), "var": var, "type": "derivative"}
            )
        elif operation == "integrate":
            original_expr = str(ai_data["equations"][0]["lhs"])
            var = ai_data["target_variables"][0]
            expr_obj = parse_expr(original_expr)
            integral_obj = sp.integrate(expr_obj, sp.Symbol(var))
            graphable.append(
                 {"name": "Original Function", "expression": str(expr_obj), "var": var, "type": "original"}
            )
            graphable.append(
                 {"name": "Integral (+ C)", "expression": str(integral_obj), "var": var, "type": "integral"}
            )
        elif operation == "simplify":
            original_expr = str(ai_data["equations"][0]["lhs"])
            simplified = sp.simplify(parse_expr(original_expr))
            var = ai_data["target_variables"][0] if ai_data.get("target_variables") else "x"
            graphable.append({"name": "Original", "expression": original_expr, "var": var, "type": "original"})
            graphable.append(
                 {"name": "Simplified", "expression": str(simplified), "var": var, "type": "simplified"}
            )
        elif operation in {"solve", "solve_system"}:
            graphable.extend(_extract_system_graphs(ai_data))
        elif operation == "limit":
            expr_str = str(ai_data["equations"][0]["lhs"])
            var = ai_data["target_variables"][0]
            graphable.append({"name": "Function", "expression": expr_str, "var": var, "type": "limit"})
        elif operation == "series":
            expr_str = str(ai_data["equations"][0]["lhs"])
            var = ai_data["target_variables"][0]
            graphable.append({"name": "Original", "expression": expr_str, "var": var, "type": "original"})
    except (TypeError, ValueError, KeyError, IndexError):
        return graphable
    return graphable
