"""UI/API presentation extraction parsers for geometry charting utilities."""

import sympy as sp
from sympy.parsing.sympy_parser import parse_expr

def extract_api_graphable_functions(operation: str, ai_data: dict, solver_output: str) -> list:
    """
    Extracts plot-ready mathematical objects to render curves on the frontend application layers.
    """
    graphable = []
    
    try:
        if operation == "derive":
            original_expr = str(ai_data["equations"][0]["lhs"])
            var = ai_data["target_variables"][0]
            
            expr_obj = parse_expr(original_expr)
            derivative_obj = sp.diff(expr_obj, sp.Symbol(var))
            
            graphable.append({"name": "Original Function", "expr": str(expr_obj), "var": var, "type": "original"})
            graphable.append({"name": "Derivative", "expr": str(derivative_obj), "var": var, "type": "derivative"})
        
        elif operation == "integrate":
            original_expr = str(ai_data["equations"][0]["lhs"])
            var = ai_data["target_variables"][0]
            
            expr_obj = parse_expr(original_expr)
            integral_obj = sp.integrate(expr_obj, sp.Symbol(var))
            
            graphable.append({"name": "Original Function", "expr": str(expr_obj), "var": var, "type": "original"})
            graphable.append({"name": "Integral (+ C)", "expr": str(integral_obj), "var": var, "type": "integral"})
        
        elif operation == "simplify":
            original_expr = str(ai_data["equations"][0]["lhs"])
            simplified = sp.simplify(parse_expr(original_expr))
            var = ai_data["target_variables"][0] if ai_data.get("target_variables") else "x"
            
            graphable.append({"name": "Original", "expr": original_expr, "var": var, "type": "original"})
            graphable.append({"name": "Simplified", "expr": str(simplified), "var": var, "type": "simplified"})
        
        elif operation == "limit":
            expr_str = str(ai_data["equations"][0]["lhs"])
            var = ai_data["target_variables"][0]
            graphable.append({"name": "Function", "expr": expr_str, "var": var, "type": "limit"})
        
        elif operation == "series":
            expr_str = str(ai_data["equations"][0]["lhs"])
            var = ai_data["target_variables"][0]
            graphable.append({"name": "Original", "expr": expr_str, "var": var, "type": "original"})
            
    except Exception:
        pass  # Gracefully fall back to returning an empty array configuration if an evaluation crash occurs
        
    return graphable