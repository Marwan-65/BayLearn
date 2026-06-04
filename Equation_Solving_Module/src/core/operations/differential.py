"""Solves Ordinary Differential Equations via analytical calculus methods."""

import sympy as sp
from sympy.parsing.sympy_parser import parse_expr
from ..formatting import format_dsolve_steps

def handle_dsolve(ai_data: dict) -> str:
    """Parses structural notations (e.g., Derivative chains) and solves ordinary differential systems."""
    dep_var_name = ai_data["target_variables"][0]
    ind_var_name = "x"
    
    dep_var = sp.Function(dep_var_name)
    ind_var = sp.Symbol(ind_var_name)
    
    try:
        local_dict = {'Derivative': lambda *args: sp.Derivative(*args), dep_var_name: dep_var, 'x': ind_var}
        lhs_expr = parse_expr(str(ai_data["equations"][0]["lhs"]), local_dict=local_dict)
        rhs_expr = parse_expr(str(ai_data["equations"][0]["rhs"]), local_dict=local_dict)
    except Exception:
        try:
            lhs_str = str(ai_data["equations"][0]["lhs"]).replace(dep_var_name, f"{dep_var_name}(x)")
            rhs_str = str(ai_data["equations"][0]["rhs"]).replace(dep_var_name, f"{dep_var_name}(x)")
            lhs_expr = parse_expr(lhs_str, local_dict={'Derivative': sp.Derivative, dep_var_name: dep_var})
            rhs_expr = parse_expr(rhs_str, local_dict={'Derivative': sp.Derivative, dep_var_name: dep_var})
        except Exception as err:
            return f"Error parsing differential equation: {err}"
            
    diff_eq = sp.Eq(lhs_expr, rhs_expr)
    
    try:
        solution = sp.dsolve(diff_eq, dep_var(ind_var))
        steps = format_dsolve_steps(diff_eq, solution, dep_var_name)
        return f"{steps}\n\nFinal Result: {solution}"
    except Exception as e:
        return f"Error solving differential equation: {e}"