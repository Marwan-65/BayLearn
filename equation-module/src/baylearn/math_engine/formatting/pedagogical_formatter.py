"""Pedagogical step formatting for all math operations."""

from typing import Any, List, Optional

import sympy as sp

from ..utils.constants import ODE_ORDER_NAMES
from .latex_utils import safe_latex
from .matrix_formatter import matrix_to_latex


def format_steps(operation: str, sympy_equations: List[sp.Eq], target_vars: List[sp.Symbol], result: Any) -> str:
    """Format generic pedagogical steps.

    Args:
        operation: Operation name.
        sympy_equations: Parsed equations.
        target_vars: Target variables.
        result: Computation result.

    Returns:
        Student-friendly multi-step text.
    """
    steps: List[str] = []
    steps.append("Step 1: Parsed input")

    if operation == "derive":
        expression = sympy_equations[0].lhs
        variable = target_vars[0]
        steps.append(f"  Expression: ${safe_latex(expression)}$")
        steps.append(f"  Differentiate with respect to: {variable}")
        steps.append("Step 2: Identify the differentiation rule(s)")

        dependent_factors = [arg for arg in expression.args if expression.is_Mul and variable in arg.free_symbols]
        if len(dependent_factors) >= 2:
            f_part = dependent_factors[0]
            g_part = sp.Mul(*dependent_factors[1:])
            steps.append("  Product rule applies: $(fg)' = f'g + fg'$")
            steps.append(f"  Here, $f = {safe_latex(f_part)}$ and $g = {safe_latex(g_part)}$")

        if expression.is_Pow and variable in expression.free_symbols:
            base, exponent = expression.as_base_exp()
            if variable in exponent.free_symbols and variable in base.free_symbols:
                steps.append("  General power rule (log differentiation) may apply.")
            elif variable in exponent.free_symbols:
                steps.append("  Exponential chain rule applies to variable exponent.")
            elif variable in base.free_symbols:
                steps.append("  Power rule applies to the base expression.")

        if expression.func in {
            sp.sin,
            sp.cos,
            sp.tan,
            sp.exp,
            sp.log,
            sp.asin,
            sp.acos,
            sp.atan,
            sp.sinh,
            sp.cosh,
            sp.tanh,
        } and expression.args:
            inner = expression.args[0]
            if variable in inner.free_symbols and sp.diff(inner, variable) != 1:
                steps.append("  Chain rule applies: $(f(g(x)))' = f'(g(x)) \\cdot g'(x)$")
                steps.append(f"  Inner function: $g({variable}) = {safe_latex(inner)}$")

        unsimplified = sp.diff(expression, variable, evaluate=False)
        steps.append("Step 3: Apply the rule formula")
        steps.append(f"  $\\frac{{d}}{{d{variable}}}\\left({safe_latex(expression)}\\right) = {safe_latex(unsimplified)}$")
        simplified = sp.simplify(result)
        if sp.simplify(unsimplified - simplified) != 0:
            steps.append("Step 4: Simplify")
            steps.append(f"  ${safe_latex(unsimplified)} = {safe_latex(simplified)}$")
        else:
            steps.append("Step 4: Final derivative")
            steps.append(f"  ${safe_latex(simplified)}$")
        return "\n".join(steps)

    if operation in ["solve", "solve_system"]:
        for index, equation in enumerate(sympy_equations, start=1):
            steps.append(f"  Equation {index}: ${safe_latex(equation.lhs)} = {safe_latex(equation.rhs)}$")
        steps.append(f"  Target variables: {[str(variable) for variable in target_vars]}")

        steps.append("Step 2: Convert to standard form (lhs - rhs = 0)")
        for index, equation in enumerate(sympy_equations, start=1):
            standard_form = sp.simplify(equation.lhs - equation.rhs)
            steps.append(f"  Eq{index}: ${safe_latex(standard_form)} = 0$")

        steps.append("Step 3: Solve the system")
        steps.append("Step 4: Final answer")
        if isinstance(result, dict):
            for variable in target_vars:
                if variable in result:
                    steps.append(f"  ${variable} = {safe_latex(result[variable])}$")
        elif isinstance(result, list):
            if result and isinstance(result[0], dict):
                for solution_index, solution in enumerate(result, start=1):
                    pieces = []
                    for variable in target_vars:
                        if variable in solution:
                            pieces.append(f"{variable} = {safe_latex(solution[variable])}")
                    steps.append(f"  Solution {solution_index}: {', '.join(pieces)}")
            else:
                if len(target_vars) == 1:
                    variable = target_vars[0]
                    for solution_index, value in enumerate(result, start=1):
                        steps.append(f"  Solution {solution_index}: ${variable} = {safe_latex(value)}$")
                else:
                    steps.append(f"  Solutions: {[safe_latex(v) for v in result]}")
        else:
            steps.append(f"  Solution: ${safe_latex(result)}$")

    elif operation == "integrate":
        expression = sympy_equations[0].lhs
        variable = target_vars[0]
        steps.append(f"  Expression: ${safe_latex(expression)}$")
        steps.append(f"  Variable of integration: {variable}")
        steps.append("Step 2: Apply integral")
        steps.append(f"  $\\int {safe_latex(expression)} \\, d{variable}$")
        steps.append("Step 3: Final antiderivative")
        steps.append(f"  ${safe_latex(result)} + C$")

    return "\n".join(steps)


def is_linear_equation(equation: sp.Eq, variables: List[sp.Symbol]) -> bool:
    """Determine whether equation is linear in the provided variables."""
    expression = sp.expand(equation.lhs - equation.rhs)
    try:
        poly = sp.Poly(expression, *variables)
    except (ValueError, TypeError):
        return False
    return poly.total_degree() <= 1


def format_student_linear_steps(
    sympy_equations: List[sp.Eq], target_vars: List[sp.Symbol], result: Any
) -> Optional[str]:
    """Format specialized educational steps for linear equations.

    Args:
        sympy_equations: Parsed equations.
        target_vars: Variables being solved.
        result: Solver output.

    Returns:
        Step text when linear-case pedagogy applies, else None.
    """
    if not sympy_equations or not target_vars:
        return None
    if not all(is_linear_equation(equation, target_vars) for equation in sympy_equations):
        return None

    standard_forms = [sp.expand(eq.lhs - eq.rhs) for eq in sympy_equations]
    steps = ["Step 1: Rewrite in standard form"]
    for index, expression in enumerate(standard_forms, start=1):
        steps.append(f"  Eq{index}: ${safe_latex(expression)} = 0$")

    if len(sympy_equations) == 1 and len(target_vars) == 1:
        variable = target_vars[0]
        expression = standard_forms[0]
        coefficient = sp.expand(expression).coeff(variable)
        constant = sp.simplify(expression - coefficient * variable)
        if coefficient == 0:
            return None
        steps.append("Step 2: Isolate the variable")
        steps.append(f"  ${safe_latex(coefficient)} \\cdot {variable} + ({safe_latex(constant)}) = 0$")
        steps.append(f"  ${safe_latex(coefficient)} \\cdot {variable} = -{safe_latex(constant)}$")
        isolated = sp.simplify(-constant / coefficient)
        steps.append(f"  ${variable} = {safe_latex(isolated)}$")
        steps.append("Step 3: Final answer")
        if isinstance(result, list):
            for solution_index, value in enumerate(result, start=1):
                steps.append(f"  Solution {solution_index}: ${variable} = {safe_latex(value)}$")
        else:
            steps.append(f"  ${variable} = {safe_latex(result)}$")
        return "\n".join(steps)

    if len(sympy_equations) == 2 and len(target_vars) == 2:
        try:
            matrix_a, matrix_b = sp.linear_eq_to_matrix(sympy_equations, target_vars)
        except (TypeError, ValueError):
            return None

        a11, a12 = matrix_a[0, 0], matrix_a[0, 1]
        a21, a22 = matrix_a[1, 0], matrix_a[1, 1]
        c1, c2 = matrix_b[0, 0], matrix_b[1, 0]
        x_var, y_var = target_vars[0], target_vars[1]

        steps.append("Step 2: Convert to coefficient form")
        steps.append(f"  Eq1: $({safe_latex(a11)}){x_var} + ({safe_latex(a12)}){y_var} = {safe_latex(c1)}$")
        steps.append(f"  Eq2: $({safe_latex(a21)}){x_var} + ({safe_latex(a22)}){y_var} = {safe_latex(c2)}$")

        determinant = sp.simplify(a11 * a22 - a21 * a12)
        if determinant == 0:
            return None

        steps.append("Step 3: Eliminate one variable using Cramer's rule")
        steps.append(
            f"  Determinant = ${safe_latex(a11)} \\cdot {safe_latex(a22)} - "
            f"{safe_latex(a21)} \\cdot {safe_latex(a12)} = {safe_latex(determinant)}$"
        )
        x_num = sp.simplify(c1 * a22 - c2 * a12)
        steps.append(f"  ${x_var} = \\frac{{{safe_latex(x_num)}}}{{{safe_latex(determinant)}}}$")
        x_value = sp.simplify(x_num / determinant)
        steps.append(f"  ${x_var} = {safe_latex(x_value)}$")

        steps.append("Step 4: Substitute back to get the second variable")
        y_num = sp.simplify(c1 - a11 * x_value)
        if a12 != 0:
            y_value = sp.simplify(y_num / a12)
            steps.append(
                f"  From Eq1: $({safe_latex(a11)}) \\cdot ({safe_latex(x_value)}) + "
                f"({safe_latex(a12)}){y_var} = {safe_latex(c1)}$"
            )
        elif a22 != 0:
            y_num = sp.simplify(c2 - a21 * x_value)
            y_value = sp.simplify(y_num / a22)
            steps.append(
                f"  From Eq2: $({safe_latex(a21)}) \\cdot ({safe_latex(x_value)}) + "
                f"({safe_latex(a22)}){y_var} = {safe_latex(c2)}$"
            )
        else:
            return None
        steps.append(f"  ${y_var} = {safe_latex(y_value)}$")

        steps.append("Step 5: Final answer")
        if isinstance(result, dict):
            steps.append(f"  ${x_var} = {safe_latex(result.get(x_var, x_value))}$")
            steps.append(f"  ${y_var} = {safe_latex(result.get(y_var, y_value))}$")
        elif isinstance(result, list) and result and isinstance(result[0], dict):
            for solution_index, solution in enumerate(result, start=1):
                parts = []
                for variable in target_vars:
                    if variable in solution:
                        parts.append(f"{variable} = {safe_latex(solution[variable])}")
                steps.append(f"  Solution {solution_index}: {', '.join(parts)}")
        else:
            steps.append(f"  ${x_var} = {safe_latex(x_value)}$")
            steps.append(f"  ${y_var} = {safe_latex(y_value)}$")
        return "\n".join(steps)

    return None


def format_dsolve_steps(diff_eq: sp.Eq, solution: Any, dep_var_name: str) -> str:
    """Format differential-equation pedagogical explanation."""
    steps: List[str] = []
    steps.append("Step 1: Classify the Differential Equation")
    lhs = diff_eq.lhs
    rhs = diff_eq.rhs
    max_order = 0

    for arg in sp.preorder_traversal(lhs):
        if isinstance(arg, sp.Derivative):
            if len(arg.args) >= 2:
                try:
                    deriv_info = arg.args[1]
                    if len(deriv_info) >= 2:
                        order = int(deriv_info[1])
                        max_order = max(max_order, order)
                    else:
                        max_order = max(max_order, 1)
                except (TypeError, ValueError):
                    max_order = max(max_order, 1)

    if max_order == 0:
        max_order = 1

    ode_order = ODE_ORDER_NAMES.get(max_order, f"{max_order}th-order") + " ODE"
    is_linear = True
    try:
        test_expr = lhs - rhs
        y_sym = sp.Symbol(dep_var_name)
        test1 = test_expr.subs(y_sym, 2 * y_sym)
        test2 = 2 * test_expr
        is_linear = sp.simplify(test1 - test2) == 0
    except (TypeError, ValueError):
        is_linear = True

    linear_status = "Linear" if is_linear else "Nonlinear"
    steps.append(f"  Type: {linear_status} {ode_order}")
    eq_latex = safe_latex(lhs - rhs) if rhs != 0 else safe_latex(lhs)
    steps.append(f"  Standard form: ${eq_latex} = 0$")
    steps.append("Step 2: What We're Looking For")
    steps.append("  We need to find $y(x)$ that satisfies the equation above.")
    steps.append("  This is called the 'general solution' because it contains arbitrary constants.")
    steps.append("Step 3: Solution Method")
    steps.append("  For this type of ODE, we use standard techniques:")
    if max_order == 1:
        steps.append("  - Check if the equation is separable (can separate $x$ and $y$)")
        steps.append("  - Or solve using integrating factor method")
    elif max_order == 2:
        steps.append("  - Form the characteristic equation")
        steps.append("  - Find the characteristic roots (can be real, complex, or repeated)")
        steps.append("  - Build the solution based on root types")
    elif max_order == 3:
        steps.append("  - Form the characteristic equation (cubic)")
        steps.append("  - Find three characteristic roots")
    else:
        steps.append("  - Use appropriate ODE solving techniques")
    steps.append("  SymPy automatically applies the best technique.")

    steps.append("Step 4: General Solution")
    solution_latex = safe_latex(solution.rhs)
    steps.append(f"  $y(x) = {solution_latex}$")
    steps.append("Step 5: Understanding the Arbitrary Constants")
    solution_rhs = solution.rhs
    constants = sorted([s for s in solution_rhs.free_symbols if "C" in str(s)], key=str)
    if constants:
        steps.append(f"  This general solution contains {len(constants)} arbitrary constant(s):")
        for const in constants:
            steps.append(f"  - ${const}$: Will be determined by initial/boundary conditions")
        steps.append("")
        steps.append("  Why arbitrary constants? Each represents a degree of freedom.")
        ode_order_name = ODE_ORDER_NAMES.get(max_order, f"{max_order}th-order")
        steps.append(f"  A {ode_order_name} ODE needs {max_order} condition(s)")
        steps.append("  to uniquely determine all constants.")

    steps.append("Step 6: Using This Solution - Finding a Particular Solution")
    steps.append("  The general solution above represents INFINITELY many functions.")
    steps.append("  To find ONE specific solution, apply initial/boundary conditions:")
    if max_order == 1:
        steps.append("  Example: Given $y(0) = 1$")
        steps.append("           Substitute to find $C_1$")
    elif max_order == 2:
        steps.append("  Example: Given $y(0) = 1$ and $y'(0) = 0$")
        steps.append("           Substitute to get system of equations")
        steps.append("           Solve to find both $C_1$ and $C_2$")
    return "\n".join(steps)


def format_matrix_steps(matrix: Any, operation: str, result: Any) -> str:
    """Format pedagogical explanation for matrix operations."""
    steps: List[str] = []
    steps.append("Step 1: Parse and Display Matrix")
    steps.append("  Input matrix:")
    matrix_latex = matrix_to_latex(matrix)
    steps.append(f"  ${matrix_latex}$")

    steps.append(f"Step 2: Apply {operation.title()} Operation")

    if operation == "determinant":
        if hasattr(matrix, "rows") and hasattr(matrix, "cols") and matrix.rows == 2 and matrix.cols == 2:
            a, b = matrix[0, 0], matrix[0, 1]
            c, d = matrix[1, 0], matrix[1, 1]
            ad = sp.simplify(a * d)
            bc = sp.simplify(b * c)
            steps.append("  Rule for 2x2: $\\det\\begin{pmatrix}a & b\\\\ c & d\\end{pmatrix} = ad-bc$")
            steps.append("Step 3: Substitute entries")
            steps.append(
                f"  $\\det(A)=({safe_latex(a)}\\cdot {safe_latex(d)})-({safe_latex(b)}\\cdot {safe_latex(c)})$"
            )
            steps.append(f"  $= {safe_latex(ad)} - {safe_latex(bc)} = {safe_latex(result)}$")
        else:
            steps.append("  For larger matrices, compute the determinant by elimination or expansion.")
            steps.append("Step 3: Determinant value")
            steps.append(f"  $\\det(A) = {safe_latex(result)}$")

    elif operation == "inverse":
        det_a = sp.simplify(matrix.det())
        steps.append("  Inverse exists iff $\\det(A) \\neq 0$.")
        if hasattr(matrix, "rows") and hasattr(matrix, "cols") and matrix.rows == 2 and matrix.cols == 2:
            a, b = matrix[0, 0], matrix[0, 1]
            c, d = matrix[1, 0], matrix[1, 1]
            ad = sp.simplify(a * d)
            bc = sp.simplify(b * c)
            steps.append("Step 3: Compute determinant to verify invertibility")
            steps.append(f"  $\\det(A)=({safe_latex(a)}\\cdot {safe_latex(d)})-({safe_latex(b)}\\cdot {safe_latex(c)})$")
            steps.append(f"  $= {safe_latex(ad)}-{safe_latex(bc)} = {safe_latex(det_a)}$")
        else:
            steps.append("Step 3: Compute determinant to verify invertibility")
            steps.append(f"  $\\det(A) = {safe_latex(det_a)}$")

        if det_a == 0:
            steps.append("Step 4: Verify condition")
            steps.append("  Since $\\det(A)=0$, the matrix is singular and has no inverse.")
            return "\n".join(steps)

        steps.append("Step 4: Verify condition")
        steps.append(f"  Since $\\det(A)={safe_latex(det_a)} \\neq 0$, inverse exists.")
        steps.append("Step 5: Compute inverse")
        steps.append(f"  $A^{{-1}} = {safe_latex(result)}$")

    elif operation == "eigenvalues":
        lam = sp.Symbol("lambda")
        char_poly = matrix.charpoly(lam)
        steps.append("  Eigenvalues are roots of the characteristic equation $\\det(A-\\lambda I)=0$.")
        steps.append("Step 3: Build characteristic equation")
        steps.append(f"  ${safe_latex(char_poly.as_expr())} = 0$")
        steps.append("Step 4: Solve for roots")
        if isinstance(result, dict) and result:
            for idx, (eigenvalue, multiplicity) in enumerate(result.items(), start=1):
                steps.append(f"  $\\lambda_{idx} = {safe_latex(eigenvalue)}$ (multiplicity {multiplicity})")
        else:
            steps.append("  Solve the polynomial equation to get all eigenvalues.")

    elif operation == "eigenvectors":
        steps.append("  For each eigenvalue, solve $(A-\\lambda I)v=0$.")
        steps.append("Step 3: Compute eigenspaces")
        if isinstance(result, list) and result:
            for idx, triple in enumerate(result, start=1):
                eigenvalue, multiplicity, vectors = triple
                steps.append(f"  Eigenvalue {idx}: $\\lambda = {safe_latex(eigenvalue)}$ (multiplicity {multiplicity})")
                for vec_idx, vector in enumerate(vectors, start=1):
                    steps.append(f"  Basis vector {vec_idx}: ${safe_latex(vector)}$")
        else:
            steps.append("  Solve each homogeneous system to obtain eigenvector basis vectors.")

    elif operation == "transpose":
        steps.append("  Transpose swaps row and column indices: $A^T_{ij}=A_{ji}$.")
        steps.append("Step 3: Write the transposed matrix")
        steps.append(f"  $A^T = {safe_latex(result)}$")

    elif operation == "rref":
        steps.append("  Apply row operations until each pivot is 1 with zeros above and below.")
        steps.append("Step 3: Reduced row-echelon form")
        steps.append(f"  $\\operatorname{{RREF}}(A) = {safe_latex(result)}$")

    elif operation == "rank":
        rref_matrix, pivots = matrix.rref()
        steps.append("  Rank equals the number of pivot columns in RREF.")
        steps.append("Step 3: Compute RREF")
        steps.append(f"  $\\operatorname{{RREF}}(A) = {safe_latex(rref_matrix)}$")
        steps.append("Step 4: Count pivot columns")
        steps.append(f"  Pivot columns: {pivots}")
        steps.append(f"  $\\operatorname{{rank}}(A) = {safe_latex(result)}$")

    elif operation == "trace":
        steps.append("  Trace is the sum of diagonal entries.")
        if hasattr(matrix, "rows") and hasattr(matrix, "cols"):
            diagonal = [matrix[i, i] for i in range(min(matrix.rows, matrix.cols))]
            diagonal_sum = " + ".join(safe_latex(v) for v in diagonal) if diagonal else "0"
            steps.append("Step 3: Substitute diagonal entries")
            steps.append(f"  $\\operatorname{{tr}}(A) = {diagonal_sum} = {safe_latex(result)}$")
        else:
            steps.append("Step 3: Compute trace")
            steps.append(f"  $\\operatorname{{tr}}(A) = {safe_latex(result)}$")

    else:
        steps.append("Step 3: Complete the operation")
        steps.append(f"  Result: ${safe_latex(result)}$")

    return "\n".join(steps)


def format_limit_steps(expression: sp.Expr, variable: sp.Symbol, approach_value: Any, direction: str, result: Any) -> str:
    """Format educational steps for limits."""
    steps: List[str] = []
    steps.append("Step 1: Identify Limit Problem")
    steps.append(f"  Expression: ${safe_latex(expression)}$")
    steps.append(f"  Variable: {variable}")
    steps.append(f"  Approaching: ${safe_latex(approach_value)}$")
    if direction == "+":
        steps.append(f"  Direction: From the right (${variable} \\to {approach_value}^+$)")
    elif direction == "-":
        steps.append(f"  Direction: From the left (${variable} \\to {approach_value}^-$)")
    else:
        steps.append("  Direction: Two-sided limit")

    steps.append("\nStep 2: Evaluate Limit")
    steps.append("  Method: Direct substitution, L'Hôpital's rule, or algebraic manipulation")
    try:
        direct = expression.subs(variable, approach_value)
        steps.append(f"  Direct substitution: ${sp.latex(direct)}$")
        if direct.has(sp.zoo) or direct.has(sp.nan):
            steps.append("  Result is indeterminate - using advanced techniques")
    except (TypeError, ValueError):
        steps.append("  Direct substitution: indeterminate form")
    steps.append("\nStep 3: Final Result")
    steps.append(f"  $\\lim_{{{variable} \\to {approach_value}}} {sp.latex(expression)} = {sp.latex(result)}$")
    return "\n".join(steps)


def format_series_steps(expression: sp.Expr, variable: sp.Symbol, point: int, order: int, result: Any) -> str:
    """Format educational steps for Taylor/Maclaurin series."""
    steps: List[str] = []
    steps.append("Step 1: Identify Series Expansion")
    steps.append(f"  Expression: ${safe_latex(expression)}$")
    steps.append(f"  Variable: {variable}")
    steps.append(f"  Expansion point (a): ${safe_latex(point)}$")
    steps.append(f"  Order: {order} terms")
    if point == 0:
        steps.append("\n  This is a Maclaurin series (Taylor series at $x=0$)")
    else:
        steps.append(f"\n  This is a Taylor series centered at $x={safe_latex(point)}$")
    steps.append("\nStep 2: Apply Taylor Formula")
    steps.append("  $f(x) = f(a) + f'(a)(x-a) + \\frac{f''(a)}{2!}(x-a)^2 + \\frac{f'''(a)}{3!}(x-a)^3 + \\ldots$")
    steps.append(f"  Compute derivatives at $x={safe_latex(point)}$ up to order {order}")
    steps.append("\nStep 3: Series Expansion")
    steps.append(f"  ${safe_latex(result)} + O({variable}^{{{order+1}}})$")
    return "\n".join(steps)


def format_partial_derivative_steps(expression: sp.Expr, variables: List[sp.Symbol], result: Any) -> str:
    """Format educational steps for partial derivatives."""
    steps: List[str] = []
    steps.append("Step 1: Identify Multivariable Function")
    steps.append(f"  Expression: ${safe_latex(expression)}$")
    steps.append(f"  Variables: {', '.join(str(v) for v in variables)}")
    steps.append("\nStep 2: Apply Partial Differentiation")
    steps.append(f"  Differentiating with respect to: {' then '.join(str(v) for v in variables)}")
    steps.append("  Treat other variables as constants at each step")
    temp_expr = expression
    for i, var in enumerate(variables, 1):
        temp_expr = sp.diff(temp_expr, var)
        steps.append(f"\n  Step 2.{i}: $\\frac{{\\partial}}{{\\partial {var}}}$")
        steps.append(f"  Result: ${safe_latex(temp_expr)}$")
    steps.append("\nStep 3: Final Partial Derivative")
    steps.append(f"  ${safe_latex(result)}$")
    return "\n".join(steps)
