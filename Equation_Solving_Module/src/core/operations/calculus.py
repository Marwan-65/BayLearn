import sympy as sp

from sympy.parsing.sympy_parser import parse_expr
from ..formatting import (
    format_base_steps, 
    format_limit_steps, 
    format_series_steps, 
    format_partial_derivative_steps,
    build_final_text_block, 
    safe_latex, 
    expr_to_clean_text
)

def handle_derive(ai_data: dict) -> str:
    
    
    expr = parse_expr(str(ai_data["equations"][0]["lhs"]))
    var = sp.Symbol(ai_data["target_variables"][0])
    derivative = sp.diff(expr, var)
    
    steps = format_base_steps("derive", [sp.Eq(expr, 0)], [var], derivative)
    final_res = build_final_text_block("derive", derivative, [var])
    
    graphs = (
        f"\n\nGraphable Functions:\n"
        f"- Original: $y = {safe_latex(expr)}$\n"
        f"- Derivative: $y = {safe_latex(derivative)}$"
    )
    return f"{steps}\n\nFinal Result:\n{final_res}{graphs}"


def handle_integrate(ai_data: dict) -> str:

    expr = parse_expr(str(ai_data["equations"][0]["lhs"]))
    var = sp.Symbol(ai_data["target_variables"][0])
    integral = sp.integrate(expr, var)
    
    steps = format_base_steps("integrate", [sp.Eq(expr, 0)], [var], integral)
    final_res = f"{build_final_text_block('integrate', integral, [var])} + C"
    
    graphs = (
        f"\n\nGraphable Functions:\n"
        f"- Original: $y = {safe_latex(expr)}$\n"
        f"- Integral: $y = {safe_latex(integral)} + C$"
    )
    return f"{steps}\n\nFinal Result:\n{final_res}{graphs}"


def handle_limit(ai_data: dict) -> str:
    try:
        expr = parse_expr(str(ai_data["equations"][0]["lhs"]))
        var = sp.Symbol(ai_data["target_variables"][0])
        approach = parse_expr(str(ai_data["equations"][0]["rhs"]))
        
        direction = ai_data.get("extra_params", {}).get("direction", "+-")
        result = sp.limit(expr, var, approach, direction if direction in ['+', '-'] else '+-')
        
        steps = format_limit_steps(expr, var, approach, direction, result)
        return f"{steps}\n\nFinal Result: {expr_to_clean_text(result)}"
    except Exception as e:
        return f"Error calculating limit: {e}"


def handle_series(ai_data: dict) -> str:
    try:
        expr = parse_expr(str(ai_data["equations"][0]["lhs"]))
        var = sp.Symbol(ai_data["target_variables"][0])
        
        params = ai_data.get("extra_params", {})
        point = int(params.get("point", 0))
        order = int(params.get("order", 6))
        
        result = sp.series(expr, var, point, order).removeO()
        steps = format_series_steps(expr, var, point, order, result)
        return f"{steps}\n\nFinal Result: {expr_to_clean_text(result)}"
    except Exception as e:
        return f"Error computing series: {e}"


def handle_partial_derivative(ai_data: dict) -> str:
    try:
        expr = parse_expr(str(ai_data["equations"][0]["lhs"]))
        variables = [sp.Symbol(v) for v in ai_data["target_variables"]]
        
        result = expr
        for var in variables:
            result = sp.diff(result, var)
            
        steps = format_partial_derivative_steps(expr, variables, result)
        return f"{steps}\n\nFinal Result: {expr_to_clean_text(result)}"
    except Exception as e:
        return f"Error computing partial derivative: {e}"