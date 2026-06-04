import sympy as sp
from sympy.parsing.sympy_parser import parse_expr

def extract_api_graphable_functions(operation: str, ai_data: dict, solver_output: str) -> list:
    """extracts the mathematical objects to graph the user's input and the result if applicable to the current operation
    """
    graphable = []
    
    try:
        if operation == "derive":
            original_expr = str(ai_data["equations"][0]["lhs"])
            var = ai_data["target_variables"][0]
            
            expr_obj = parse_expr(original_expr)
            derivative_obj = sp.diff(expr_obj, sp.Symbol(var))
            
            graphable.append({"name": "Original Function", "expression": str(expr_obj), "var": var, "type": "original", "analysis": _analyze_expression(expr_obj, var)})
            graphable.append({"name": "Derivative", "expression": str(derivative_obj), "var": var, "type": "derivative", "analysis": _analyze_expression(derivative_obj, var)})
        elif operation == "dsolve":
            original_expr = str(ai_data["equations"][0]["lhs"])
            var = ai_data["target_variables"][0]
            
            expr_obj = parse_expr(original_expr)
            solution_obj = sp.dsolve(expr_obj, sp.Function(var))
            
            graphable.append({"name": "Differential Equation", "expression": str(expr_obj), "var": var, "type": "differential_equation", "analysis": _analyze_expression(expr_obj, var)})
            graphable.append({"name": "General Solution", "expression": str(solution_obj), "var": var, "type": "differential_solution", "analysis": _analyze_expression(solution_obj, var)})
        
        elif operation == "integrate":
            original_expr = str(ai_data["equations"][0]["lhs"])
            var = ai_data["target_variables"][0]
            
            expr_obj = parse_expr(original_expr)
            integral_obj = sp.integrate(expr_obj, sp.Symbol(var))
            
            graphable.append({"name": "Original Function", "expression": str(expr_obj), "var": var, "type": "original", "analysis": _analyze_expression(expr_obj, var)})
            graphable.append({"name": "Integral (+ C)", "expression": str(integral_obj), "var": var, "type": "integral", "analysis": _analyze_expression(integral_obj, var)})
        
        elif operation == "simplify":
            original_expr = str(ai_data["equations"][0]["lhs"])
            simplified = sp.simplify(parse_expr(original_expr))
            var = ai_data["target_variables"][0] if ai_data.get("target_variables") else "x"
            
            graphable.append({"name": "Original", "expression": original_expr, "var": var, "type": "original", "analysis": _analyze_expression(parse_expr(original_expr), var)})
            graphable.append({"name": "Simplified", "expression": str(simplified), "var": var, "type": "simplified", "analysis": _analyze_expression(simplified, var)})
        
        elif operation == "limit":
            expr_str = str(ai_data["equations"][0]["lhs"])
            var = ai_data["target_variables"][0]
            graphable.append({"name": "Function", "expression": expr_str, "var": var, "type": "limit", "analysis": _analyze_expression(parse_expr(expr_str), var)})
        
        elif operation == "series":
            expr_str = str(ai_data["equations"][0]["lhs"])
            var = ai_data["target_variables"][0]
            graphable.append({"name": "Original", "expression": expr_str, "var": var, "type": "original", "analysis": _analyze_expression(parse_expr(expr_str), var)})
        elif operation in ["solve", "solve_system"]:
            x_sym = sp.Symbol("x")
            y_sym = sp.Symbol("y")
            
            for idx, eq_data in enumerate(ai_data.get("equations", [])):
                try:
                    lhs = parse_expr(str(eq_data["lhs"]))
                    rhs = parse_expr(str(eq_data["rhs"]))
                    equation = sp.Eq(lhs, rhs)
                    
                    # Check if y exists in the equation
                    if not equation.has(y_sym):
                        # if it doesn't have a 2nd variable then it's a 1d equation
                        # We graph it by moving everything to one side-> y = LHS - RHS
                        expression_to_graph = lhs - rhs
                        label = f"Eq {idx + 1}"
                        graphable.append({
                            "name": label,
                            "expression": str(expression_to_graph),
                            "var": "x",
                            "type": "polynomial",
                            "analysis": _analyze_expression(expression_to_graph, "x")
                        })
                    else:
                        # otherwise if it's a 2D equation (like 2x + y = 10) we solve for y
                        y_solutions = sp.solve(equation, y_sym)
                        
                        for sol_idx, branch in enumerate(y_solutions):
                            if not branch.has(y_sym):
                                label = f"Eq {idx + 1}" if len(y_solutions) == 1 else f"Eq {idx + 1} (branch {sol_idx + 1})"
                                graphable.append({
                                    "name": label,
                                    "expression": str(branch),
                                    "var": "x",
                                    "type": "linear_branch",
                                    "analysis": _analyze_expression(branch, "x")
                                })
                except Exception:
                    continue  # skip equations that fail to parse or solve, allowing others to be processed
    except Exception:
        pass
        
    return graphable
def _analyze_expression(expr_obj, var_name: str) -> dict:
    
    try:
        var = sp.Symbol(var_name)
        first_derivative = sp.diff(expr_obj, var)
        second_derivative = sp.diff(first_derivative, var)
        
        analysis = {
            "symmetry": "No symmetry",
            "critical_points": [],
            "inflection_points": [],
            "x_intercepts": [],
            "y_intercept": None
        }

        # check for symmetry: even, odd, or none
        if sp.simplify(expr_obj.subs(var, -var) - expr_obj) == 0:
            analysis["symmetry"] = "Even (Symmetric about Y-axis)"
        elif sp.simplify(expr_obj.subs(var, -var) + expr_obj) == 0:
            analysis["symmetry"] = "Odd (Symmetric about Origin)"

        # intercept with the axies
        try:
            x_ints = sp.solve(sp.Eq(expr_obj, 0), var)
            analysis["x_intercepts"] = [f"{float(sp.N(r)):.3f}" for r in x_ints if r.is_real]
        except Exception:
            pass #skip if not possible for complex eqs

        try:
            y_int = expr_obj.subs(var, 0)
            if y_int.is_real:
                analysis["y_intercept"] = f"{float(sp.N(y_int)):.3f}"
        except Exception:
            pass

        # critical points (min/max) first derivative is 0 and 2nd derivative
        # identifies if min or max
        try:
            crit_points = sp.solve(sp.Eq(first_derivative, 0), var)
            for cp in crit_points:
                if cp.is_real:
                    y_cp = expr_obj.subs(var, cp)
                    concavity = "Minimum" if float(sp.N(second_derivative.subs(var, cp))) > 0 else "Maximum"
                    analysis["critical_points"].append(
                        f"Local {concavity} at ({float(sp.N(cp)):.3f}, {float(sp.N(y_cp)):.3f})"
                    )
        except Exception:
            pass

        # inflection points where 2nd derivative is zero
        try:
            inf_points = sp.solve(sp.Eq(second_derivative, 0), var)
            for ip in inf_points:
                if ip.is_real:
                    y_ip = expr_obj.subs(var, ip)
                    analysis["inflection_points"].append(
                        f"({float(sp.N(ip)):.3f}, {float(sp.N(y_ip)):.3f})"
                    )
        except Exception:
            pass

        return analysis
    except Exception:
        return None