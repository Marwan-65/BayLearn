"""math explanation in steps for students to follow along"""

import sympy as sp
from typing import List, Dict, Any, Union
from .latex import safe_latex, expr_to_clean_text, matrix_to_latex

def format_base_steps(operation: str, sympy_equations: List[sp.Eq], target_vars: List[sp.Symbol], result: Any) -> str:
    steps = ["Step 1: Parsed input"]

    if operation == "derive":
        expr = sympy_equations[0].lhs
        var = target_vars[0]
        steps.append(f"  Expression: ${safe_latex(expr)}$")
        steps.append(f"  Differentiate with respect to: {var}")
        steps.append("Step 2: Apply derivative")
        # FIXED: Using rf"..." so \f in \frac doesn't turn into a Form Feed
        steps.append(rf"  $\frac{{d}}{{d{var}}} {safe_latex(expr)}$")
        steps.append("Step 3: Derivative")
        steps.append(f"  ${safe_latex(result)}$")
        return "\n".join(steps)

    if operation in ["solve", "solve_system"]:
        for idx, eq in enumerate(sympy_equations, start=1):
            steps.append(f"  Equation {idx}: ${safe_latex(eq.lhs)} = {safe_latex(eq.rhs)}$")
        steps.append(f"  Target variables: {[str(v) for v in target_vars]}")
        steps.append("Step 2: Convert to standard form (lhs - rhs = 0)")
        for idx, eq in enumerate(sympy_equations, start=1):
            std_form = sp.simplify(eq.lhs - eq.rhs)
            steps.append(f"  Eq{idx}: ${safe_latex(std_form)} = 0$")
        steps.append("Step 3: Solve the system")
        steps.append("Step 4: Final answer")
        
        if isinstance(result, dict):
            for var in target_vars:
                if var in result:
                    steps.append(f"  ${var} = {safe_latex(result[var])}$")
        elif isinstance(result, list):
            if result and isinstance(result[0], dict):
                for s_idx, sol in enumerate(result, start=1):
                    pieces = [f"{v} = {safe_latex(sol[v])}" for v in target_vars if v in sol]
                    steps.append(f"  Solution {s_idx}: {', '.join(pieces)}")
            else:
                if len(target_vars) == 1:
                    var = target_vars[0]
                    for s_idx, val in enumerate(result, start=1):
                        if isinstance(val, tuple) and len(val) == 1:
                            val = val[0]
                        steps.append(f"  Solution {s_idx}: ${var} = {safe_latex(val)}$")
                else:
                    steps.append(f"  Solutions: {[safe_latex(v) for v in result]}")
        else:
            steps.append(f"  Solution: ${safe_latex(result)}$")
        return "\n".join(steps)

    if operation == "integrate":
        expr = sympy_equations[0].lhs
        var = target_vars[0]
        steps.append(f"  Expression: ${safe_latex(expr)}$")
        steps.append(f"  Variable of integration: {var}")
        steps.append("Step 2: Apply integral")
        # FIXED: Using rf"..." for \int and \,
        steps.append(rf"  $\int {{ {safe_latex(expr)} }} \, d{var}$")
        steps.append("Step 3: Final antiderivative")
        steps.append(f"  ${safe_latex(result)} + C$")
        return "\n".join(steps)

    return "\n".join(steps)

def format_student_linear_steps(sympy_equations: List[sp.Eq], target_vars: List[sp.Symbol], result: Any) -> Union[str, None]:

    if not sympy_equations or not target_vars:
        return None

    for eq in sympy_equations:
        expr = sp.expand(eq.lhs - eq.rhs)
        try:
            if sp.Poly(expr, *target_vars).total_degree() > 1:
                return None
        except (ValueError, TypeError):
            return False

    std_forms = [sp.expand(eq.lhs - eq.rhs) for eq in sympy_equations]
    steps = ["Step 1: Rewrite in standard form"]
    for idx, expr in enumerate(std_forms, start=1):
        steps.append(f"  Eq{idx}: ${safe_latex(expr)} = 0$")

    if len(sympy_equations) == 1 and len(target_vars) == 1:
        var = target_vars[0]
        expr = std_forms[0]
        coeff = sp.expand(expr).coeff(var)
        constant = sp.simplify(expr - coeff * var)
        if coeff == 0:
            return None
            
        steps.append("Step 2: Isolate the variable")
        # using rf"..." for \times to avoid wrong rendering in fe
        steps.append(rf"  ${safe_latex(coeff)} \times {var} + ({safe_latex(constant)}) = 0$")
        steps.append(rf"  ${safe_latex(coeff)} \times {var} = -{safe_latex(constant)}$")
        isolated = sp.simplify(-constant / coeff)
        steps.append(f"  ${var} = {safe_latex(isolated)}$")
        steps.append("Step 3: Final answer")
        
        if isinstance(result, list):
            for s_idx, val in enumerate(result, start=1):
                if isinstance(val, tuple) and len(val) == 1:
                    val = val[0]
                steps.append(f"  Solution {s_idx}: ${var} = {safe_latex(val)}$")
        else:
            steps.append(f"  ${var} = {safe_latex(result)}$")
        return "\n".join(steps)

    if len(sympy_equations) == 2 and len(target_vars) == 2:
        try:
            mat_A, mat_B = sp.linear_eq_to_matrix(sympy_equations, target_vars)
        except Exception:
            return None

        a11, a12, a21, a22 = mat_A[0, 0], mat_A[0, 1], mat_A[1, 0], mat_A[1, 1]
        c1, c2 = mat_B[0, 0], mat_B[1, 0]
        x_var, y_var = target_vars[0], target_vars[1]

        steps.append("Step 2: Convert to coefficient form")
        steps.append(f"  Eq1: $({safe_latex(a11)}){x_var} + ({safe_latex(a12)}){y_var} = {safe_latex(c1)}$")
        steps.append(f"  Eq2: $({safe_latex(a21)}){x_var} + ({safe_latex(a22)}){y_var} = {safe_latex(c2)}$")

        det = sp.simplify(a11 * a22 - a21 * a12)
        if det == 0:
            return None

        steps.append("Step 3: Eliminate one variable using Cramer's rule")
        steps.append(rf"  Determinant = ${safe_latex(a11)} \times {safe_latex(a22)} - {safe_latex(a21)} \times {safe_latex(a12)} = {safe_latex(det)}$")
        x_num = sp.simplify(c1 * a22 - c2 * a12)
        steps.append(rf"  ${x_var} = \frac{{{safe_latex(x_num)}}}{{{safe_latex(det)}}}$")
        x_val = sp.simplify(x_num / det)
        steps.append(f"  ${x_var} = {safe_latex(x_val)}$")

        steps.append("Step 4: Substitute back to get the second variable")
        if a12 != 0:
            y_val = sp.simplify((c1 - a11 * x_val) / a12)
            steps.append(rf"  From Eq1: $({safe_latex(a11)}) \times ({safe_latex(x_val)}) + ({safe_latex(a12)}){y_var} = {safe_latex(c1)}$")
        elif a22 != 0:
            y_val = sp.simplify((c2 - a21 * x_val) / a22)
            steps.append(rf"  From Eq2: $({safe_latex(a21)}) \times ({safe_latex(x_val)}) + ({safe_latex(a22)}){y_var} = {safe_latex(c2)}$")
        else:
            return None
        steps.append(f"  ${y_var} = {safe_latex(y_val)}$")
        steps.append("Step 5: Final answer")
        
        if isinstance(result, dict):
            steps.append(f"  ${x_var} = {safe_latex(result.get(x_var, x_val))}$")
            steps.append(f"  ${y_var} = {safe_latex(result.get(y_var, y_val))}$")
        else:
            steps.append(f"  ${x_var} = {safe_latex(x_val)}$")
            steps.append(f"  ${y_var} = {safe_latex(y_val)}$")
        return "\n".join(steps)

    return None

def format_dsolve_steps(diff_eq: sp.Eq, solution: sp.Eq, dep_var_name: str) -> str:
    steps = ["Step 1: Classify the Differential Equation"]
    lhs, rhs = diff_eq.lhs, diff_eq.rhs
    
    max_order = 0
    for arg in sp.preorder_traversal(lhs):
        if isinstance(arg, sp.Derivative) and len(arg.args) >= 2:
            try:
                deriv_info = arg.args[1]
                max_order = max(max_order, int(deriv_info[1]) if len(deriv_info) >= 2 else 1)
            except Exception:
                max_order = max(max_order, 1)
                
    if max_order == 0: max_order = 1
        
    order_names = {1: "1st-order", 2: "2nd-order", 3: "3rd-order"}
    ode_order = order_names.get(max_order, f"{max_order}th-order") + " ODE"
    
    is_linear = True
    try:
        y_sym = sp.Symbol(dep_var_name)
        test_expr = lhs - rhs
        is_linear = sp.simplify(test_expr.subs(y_sym, 2*y_sym) - (2 * test_expr)) == 0
    except Exception:
        pass
        
    steps.append(f"  Type: {'Linear' if is_linear else 'Nonlinear'} {ode_order}")
    eq_latex = safe_latex(lhs - rhs) if rhs != 0 else safe_latex(lhs)
    steps.append(f"  Standard form: ${eq_latex} = 0$")
    
    steps.append("Step 2: What We're Looking For")
    steps.append(f"  We need to find $y(x)$ that satisfies the equation above.")
    steps.append("  This is called the 'general solution' because it contains arbitrary constants.")
    
    steps.append("Step 3: Solution Method")
    steps.append("  For this type of ODE, we use standard techniques:")
    if max_order == 1:
        steps.append("  - Check if the equation is separable (can separate $x$ and $y$)\n  - Or solve using integrating factor method")
    elif max_order == 2:
        steps.append("  - Form the characteristic equation\n  - Find the characteristic roots\n  - Build the solution based on root types")
    else:
        steps.append("  - Use appropriate ODE solving techniques")
        
    steps.append("Step 4: General Solution")
    steps.append(f"  $y(x) = {safe_latex(solution.rhs)}$")
    
    constants = sorted([s for s in solution.rhs.free_symbols if 'C' in str(s)], key=str)
    if constants:
        steps.append("Step 5: Understanding the Arbitrary Constants")
        steps.append(f"  This general solution contains {len(constants)} arbitrary constant(s):")
        for const in constants:
            steps.append(f"  - ${const}$: Will be determined by initial/boundary conditions")
        steps.append(f"\n  A {order_names.get(max_order, f'{max_order}th-order')} ODE needs {max_order} condition(s) to isolate specific curves.")
        
    steps.append("Step 6: Using This Solution - Finding a Particular Solution")
    steps.append("  To find ONE specific solution, apply initial/boundary conditions via substitution.")
    return "\n".join(steps)

def format_matrix_steps(matrix: sp.Matrix, operation: str, result: Any) -> str:
    steps = ["Step 1: Parse and Display Matrix", "", "Input Matrix:", f"$$ {matrix_to_latex(matrix)} $$", ""]
    steps.append(f"Step 2: Apply {operation.title()} Operation")
    def _val(expr): return expr_to_clean_text(expr)
        
    rows, cols = getattr(matrix, 'rows', 0), getattr(matrix, 'cols', 0)
    is_square = (rows == cols) and (rows > 0)
    
    if operation == "determinant":
        if rows == 2:
            a, b, c, d = matrix[0, 0], matrix[0, 1], matrix[1, 0], matrix[1, 1]
            steps.append("\n  For a 2×2 matrix, the formula is: ad - bc")
            steps.append(f"  = ({_val(a)})({_val(d)}) - ({_val(b)})({_val(c)})")
            steps.append(f"  = {_val(a*d)} - {_val(b*c)}")
            steps.append(f"  = {_val(result)}")
        else:
            steps.append("  Method: Using cofactor expansion or row reduction.")
    elif operation == "trace":
        if is_square:
            steps.append(f"  = {_val(result)}")
    return "\n".join(steps)

def format_limit_steps(expression, variable, approach_value, direction: str, result: Any) -> str:
    if direction == '+':
        dir_text = f"From right (${variable} \\to {safe_latex(approach_value)}^+$)"
    elif direction == '-':
        dir_text = f"From left (${variable} \\to {safe_latex(approach_value)}^-$)"
    else:
        dir_text = "Two-sided limit"

    steps = [
        "Step 1: Identify Limit Problem",
        f"  Expression: ${safe_latex(expression)}$",
        f"  Variable: {variable}",
        f"  Approaching: ${safe_latex(approach_value)}$",
        f"  Direction: {dir_text}",
        "Step 2: Evaluate Limit",
        "  Method: Direct substitution, L'Hôpital's rule, or algebraic factoring.",
    ]
    try:
        direct = expression.subs(variable, approach_value)
        steps.append(f"  Direct substitution attempt yields: ${safe_latex(direct)}$")
    except Exception:
        steps.append("  Direct substitution results in an indeterminate configuration.")

    steps.append("Step 3: Final Result")
    steps.append(rf"  $\lim_{{{variable} \to {safe_latex(approach_value)}}} {safe_latex(expression)} = {safe_latex(result)}$")
    return "\n".join(steps)

def format_series_steps(expression, variable, point, order, result) -> str:
    steps = [
        "Step 1: Identify Series Expansion",
        f"  Expression: ${safe_latex(expression)}$",
        f"  Variable: {variable}",
        f"  Expansion point (a): ${safe_latex(point)}$",
        f"  Order limit: {order} terms",
        f"  This is a {'Maclaurin' if point == 0 else 'Taylor'} series expansion.",
        "Step 2: Apply Taylor Formula",
        rf"  $f(x) = f(a) + f'(a)(x-a) + \frac{{f''(a)}}{{2!}}(x-a)^2 + \ldots$",
        "Step 3: Series Expansion",
        rf"  ${safe_latex(result)} + O({variable}^{{{order+1}}})$",
    ]
    return "\n".join(steps)

def format_partial_derivative_steps(expression, variables, result) -> str:
    steps = [
        "Step 1: Identify Multivariable Function",
        f"  Expression: ${safe_latex(expression)}$",
        f"  Variables: {', '.join(str(v) for v in variables)}",
        "Step 2: Apply Partial Differentiation",
        f"  Differentiating step-by-step with respect to: {' then '.join(str(v) for v in variables)}",
    ]
    temp_expr = expression
    for idx, var in enumerate(variables, 1):
        temp_expr = sp.diff(temp_expr, var)
        steps.append(rf"  Step 2.{idx}: Apply $\frac{{\partial}}{{\partial {var}}}$")
        steps.append(f"  Result: ${safe_latex(temp_expr)}$")
    steps.append("Step 3: Final Partial Derivative")
    steps.append(f"  ${safe_latex(result)}$")
    return "\n".join(steps)

def build_final_text_block(operation: str, result: Any, target_vars: List[sp.Symbol]) -> str:
    """Always returns a $...$ wrapped string so the frontend renders it as math, never raw LaTeX."""
    if operation in ["derive", "integrate", "simplify", "partial_derivative", "limit", "series"]:
        return f"${safe_latex(result)}$"
    if operation == "matrix_ops":
        return str(result)

    if isinstance(result, dict):
        # All inside one $...$ block — \quad is valid KaTeX spacing
        inner = r" \quad ".join(f"{v} = {safe_latex(result[v])}" for v in target_vars if v in result)
        return f"${inner}$"

    if isinstance(result, list) and len(target_vars) == 1:
        v = target_vars[0]
        parts = []
        for i, val in enumerate(result, 1):
            if isinstance(val, tuple) and len(val) == 1:
                val = val[0]
            parts.append(rf"\text{{Sol {i}: }} {v} = {safe_latex(val)}")
        return "$" + r" \quad \mid \quad ".join(parts) + "$"

    if isinstance(result, list) and result and isinstance(result[0], tuple):
        parts = []
        for s_idx, values in enumerate(result, start=1):
            assigns = [f"{target_vars[v_idx]} = {safe_latex(val)}"
                       for v_idx, val in enumerate(values) if v_idx < len(target_vars)]
            parts.append(r"\text{Sol " + str(s_idx) + r": }" + ", ".join(assigns))
        return "$" + r" \quad \mid \quad ".join(parts) + "$"

    return f"${expr_to_clean_text(result)}$"