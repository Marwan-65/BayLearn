"""Symbolic operations for equation systems solving and basic term simplifications."""

import sympy as sp
from sympy.parsing.sympy_parser import parse_expr
from ..formatting import (
    format_student_linear_steps, 
    format_base_steps, 
    build_final_text_block, 
    expr_to_clean_text
)

def handle_solve(ai_data: dict) -> str:
    """Parses and computes algebraic intersections for systems of symbols."""
    sympy_equations = []
    for eq_data in ai_data["equations"]:
        lhs = parse_expr(str(eq_data["lhs"]))
        rhs = parse_expr(str(eq_data["rhs"]))
        sympy_equations.append(sp.Eq(lhs, rhs))
        
    target_vars = [sp.Symbol(var) for var in ai_data["target_variables"]]
    solutions = sp.solve(sympy_equations, target_vars)
    
    steps = format_student_linear_steps(sympy_equations, target_vars, solutions)
    if steps is None:
        steps = format_base_steps(ai_data["operation"], sympy_equations, target_vars, solutions)
        
    final_res = build_final_text_block(ai_data["operation"], solutions, target_vars)
    return f"{steps}\n\nFinal Result: {final_res}"


def handle_simplify(ai_data: dict) -> str:
    """Simplifies complex expressions into concise equivalent equations."""
    try:
        expression = parse_expr(str(ai_data["equations"][0]["lhs"]))
        result = sp.simplify(expression)
        
        steps = [
            "Step 1: Original Expression",
            f"  {expr_to_clean_text(expression)}",
            "\nStep 2: Apply Simplification",
            "  Using algebraic rules, identity maps, or factoring combinations.",
            "\nStep 3: Simplified Result",
            f"  {expr_to_clean_text(result)}"
        ]
        return f"\n".join(steps) + f"\n\nFinal Result: {expr_to_clean_text(result)}"
    except Exception as e:
        return f"Error simplifying expression: {e}"