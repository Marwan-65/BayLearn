import json
import os
import re
import sympy as sp
from sympy.parsing.sympy_parser import parse_expr
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GROQ_API_KEY")

# Initialize the Groq client (make sure your API key is in your environment variables)
client = Groq(api_key=api_key)

system_prompt = """
You are a mathematical translation API. 
Read the user's messy mathematical input and translate it into strict, unambiguous SymPy-compatible syntax.
1. Fix human typos and ambiguities (e.g., if 'x' is used as a multiplication sign, replace it with '*').
2. Identify the core mathematical operation from: 'solve', 'solve_system', 'derive', 'integrate', 'dsolve', 'matrix_ops', 'limit', 'series', 'simplify', 'partial_derivative'.
3. Format the equations as a list of objects. Each object must have a "lhs" and "rhs".
-ALL values for "lhs" and "rhs" MUST be formatted as strings, even if they are plain numbers. 
4. Identify the target variables and return them as a list of strings.
5. Output ONLY a valid JSON object with these exact keys: "operation", "equations", "target_variables", and optionally "matrix_operation" or "extra_params". Do not include markdown.
6. For 'derive' and 'integrate' operations, place the actual mathematical expression STRICTLY in the "lhs" and set "rhs" to "0".
7. For 'dsolve' (differential equations), convert notation like dy/dx, y', or D(y, x) into SymPy's Derivative syntax:
   - Replace dy/dx with Derivative(y, x)
   - Replace y' with Derivative(y, x)
   - Replace D(y, x) with Derivative(y, x)
   - Place the differential equation in "lhs" format like "Derivative(y, x) - expression" or "Derivative(y, x) = expression" in "lhs = rhs" form
   - Target variable should be the function being solved for (e.g., "y" not "x")
8. For 'matrix_ops', format matrices as Matrix([[a,b],[c,d]]) syntax in "lhs". REQUIRED: Set "matrix_operation" field to EXACTLY one of these strings: "determinant", "inverse", "eigenvalues", "eigenvectors", "transpose", "rref", "rank", "trace". Look for keywords in user input like "find determinant", "calculate inverse", "get eigenvalues", etc.
   Examples:
   - "Find determinant of [[1,2],[3,4]]" → {"operation": "matrix_ops", "matrix_operation": "determinant", "equations": [{"lhs": "Matrix([[1,2],[3,4]])", "rhs": "0"}]}
   - "Calculate inverse of [[2,1],[1,3]]" → {"operation": "matrix_ops", "matrix_operation": "inverse", "equations": [{"lhs": "Matrix([[2,1],[1,3]])", "rhs": "0"}]}
   - "Get eigenvalues of [[4,-2],[1,1]]" → {"operation": "matrix_ops", "matrix_operation": "eigenvalues", "equations": [{"lhs": "Matrix([[4,-2],[1,1]])", "rhs": "0"}]}
9. For 'limit', format as: lhs="expression", rhs="approach_value", target_variables=["variable"]. Add "extra_params": {"direction": "+", "-", or "+-"} for one-sided limits.
10. For 'series', format as: lhs="expression", target_variables=["variable"], extra_params={"point": "0", "order": "6"} for Taylor series.
11. For 'partial_derivative', format as: lhs="expression", target_variables=["var1", "var2",...] for the order of differentiation.
12. For 'simplify', place expression in "lhs", set rhs="0".
NEVER use abstract function labels like "f(x)", "y", or "y(x)".
13. Translate standard mathematical functions into explicit SymPy syntax: 
- Euler's number 'e^x' MUST become 'exp(x)' (never 'e**x').
- Natural log 'ln(x)' MUST become 'log(x)'.
- Square root 'sqrt(x)' MUST become 'sqrt(x)'.
"""

def _is_valid_latex(latex_str):
    """Check if a LaTeX string is valid for rendering."""
    if not latex_str:
        return False
    
    # Check for balanced braces
    if latex_str.count('{') != latex_str.count('}'):
        return False
    
    # Check for balanced parentheses
    if latex_str.count('(') != latex_str.count(')'):
        return False
    
    # Check for problematic patterns
    problematic = ['\\left\\left', '\\right\\right', '{{{{', '}}}}', '}$', '$}']
    if any(pattern in latex_str for pattern in problematic):
        return False
    
    # Check reasonable length
    if len(latex_str) > 500:
        return False
    
    return True


def _sanitize_latex(latex_str):
    """Sanitize LaTeX string to fix common formatting issues."""
    if not latex_str:
        return latex_str
    
    # Only sanitize if it looks like LaTeX (contains backslashes or braces)
    if '\\' not in latex_str and '{' not in latex_str and '}' not in latex_str:
        return latex_str
    
    # Remove excessive whitespace (only for LaTeX)
    latex_str = re.sub(r'\s+', ' ', latex_str.strip())
    
    # Fix common brace issues
    latex_str = re.sub(r'\{\{+', '{', latex_str)  # Multiple opening braces
    latex_str = re.sub(r'\}+\}', '}', latex_str)  # Multiple closing braces
    latex_str = re.sub(r'\}\{', '}{', latex_str)  # Adjacent braces (keep as is)
    
    # Fix unmatched \left and \right
    latex_str = re.sub(r'\\left\\left', '\\left', latex_str)
    latex_str = re.sub(r'\\right\\right', '\\right', latex_str)
    
    # Count and balance braces
    open_braces = latex_str.count('{')
    close_braces = latex_str.count('}')
    
    # Add missing closing braces
    if open_braces > close_braces:
        latex_str += '}' * (open_braces - close_braces)
    
    # Remove extra closing braces from the end
    while latex_str.endswith('}') and latex_str.count('}') > latex_str.count('{'):
        latex_str = latex_str[:-1]
    
    # Balance parentheses  
    open_parens = latex_str.count('(')
    close_parens = latex_str.count(')')
    
    if open_parens > close_parens:
        latex_str += ')' * (open_parens - close_parens)
    elif close_parens > open_parens:
        # Remove extra closing parens from end
        while latex_str.endswith(')') and latex_str.count(')') > latex_str.count('('):
            latex_str = latex_str[:-1]
    
    return latex_str


def _format_long_expression(expr, max_length=60):
    """Format long mathematical expressions for better readability."""
    try:
        latex_str = _safe_latex(expr)
        
        # If the expression is short enough, return as is
        if len(latex_str) <= max_length:
            return latex_str
        
        # Try to break at logical points
        # Look for + or - operators at the top level
        if '+' in latex_str or '-' in latex_str:
            # Split on operators but keep them
            parts = []
            current_part = ""
            brace_level = 0
            
            for i, char in enumerate(latex_str):
                if char == '{':
                    brace_level += 1
                elif char == '}':
                    brace_level -= 1
                
                current_part += char
                
                # Split at top-level + or - operators
                if brace_level == 0 and char in ['+', '-'] and i > 0:
                    if len(current_part.strip()) > 0:
                        parts.append(current_part.strip())
                        current_part = ""
                
                # Also split if current part is getting too long
                elif len(current_part) > max_length and brace_level == 0:
                    parts.append(current_part.strip())
                    current_part = ""
            
            # Add the remaining part
            if current_part.strip():
                parts.append(current_part.strip())
            
            # If we have multiple parts, format them nicely
            if len(parts) > 1:
                # Clean up the parts
                formatted_parts = []
                for i, part in enumerate(parts):
                    part = part.strip()
                    if i > 0 and not part.startswith(('+', '-')):
                        part = '+' + part
                    formatted_parts.append(part)
                
                return ' \\\\\n\\quad '.join(formatted_parts)
        
        # If we couldn't break it nicely, return the original
        return latex_str
        
    except Exception:
        return _safe_latex(expr)


def _safe_latex(expr):
    """Safely convert expression to LaTeX, handling potential formatting issues."""
    try:
        # First try to get the LaTeX string from SymPy
        latex_str = sp.latex(expr)
        
        # Sanitize the LaTeX string
        latex_str = _sanitize_latex(latex_str)
        
        # Final validation
        if not _is_valid_latex(latex_str):
            return _expr_text(expr)
            
        return latex_str
        
    except Exception:
        # If anything fails, fall back to readable text format
        try:
            return _expr_text(expr)
        except:
            return str(expr)


def _is_valid_latex(latex_str):
    """Check if a LaTeX string is valid for rendering."""
    if not latex_str:
        return False
    
    # Check for balanced braces
    if latex_str.count('{') != latex_str.count('}'):
        return False
    
    # Check for balanced parentheses
    if latex_str.count('(') != latex_str.count(')'):
        return False
    
    # Check for problematic patterns
    problematic = ['\\left\\left', '\\right\\right', '{{{{', '}}}}', '}$', '$}']
    if any(pattern in latex_str for pattern in problematic):
        return False
    
    # Check reasonable length
    if len(latex_str) > 500:
        return False
    
    return True


def _matrix_to_latex(matrix):
    """Convert a SymPy matrix to LaTeX format for beautiful display."""
    if not hasattr(matrix, 'rows') or not hasattr(matrix, 'cols'):
        # Not a matrix, try to convert to LaTeX anyway
        return _safe_latex(matrix)
    
    # Use SymPy's built-in LaTeX conversion for matrices
    return _safe_latex(matrix)


def _format_matrix_display(matrix):
    """Format a SymPy matrix for clean display with proper rows and columns."""
    if not hasattr(matrix, 'rows') or not hasattr(matrix, 'cols'):
        return str(matrix)
    
    rows = matrix.rows
    cols = matrix.cols
    
    # Convert matrix to list of lists
    matrix_data = []
    for i in range(rows):
        row = []
        for j in range(cols):
            element = matrix[i, j]
            # Format each element nicely
            element_str = _expr_text(element)
            row.append(element_str)
        matrix_data.append(row)
    
    # Calculate column widths for alignment
    col_widths = []
    for j in range(cols):
        max_width = max(len(matrix_data[i][j]) for i in range(rows))
        col_widths.append(max_width)
    
    # Build the formatted string
    lines = []
    lines.append("┌" + " " * (sum(col_widths) + 3 * (cols - 1) + 2) + "┐")
    
    for i in range(rows):
        row_strs = []
        for j in range(cols):
            # Right-align numbers for better appearance
            element = matrix_data[i][j].rjust(col_widths[j])
            row_strs.append(element)
        lines.append("│ " + "   ".join(row_strs) + " │")
    
    lines.append("└" + " " * (sum(col_widths) + 3 * (cols - 1) + 2) + "┘")
    
    return "\n".join(lines)


def _expr_text(expr):
    try:
        return sp.sstr(sp.simplify(expr)).replace("**", "^")
    except Exception:
        return sp.sstr(expr).replace("**", "^")

def _expr_to_readable_text(expr):
    """Convert sympy expression to readable text format (not LaTeX)."""
    text = sp.sstr(expr)  # Use string representation, not LaTeX
    text = text.replace("**", "^")  # Exponents: 2**3 → 2^3
    text = text.replace(" ", "")     # Remove spaces: x**2 + 3*x → x^2+3*x
    return text

def _final_text(operation, result, target_vars):
    if operation in ["derive", "integrate", "simplify", "partial_derivative", "limit", "series"]:
        return f"${_safe_latex(result)}$"
    
    if operation in ["matrix_ops"]:
        return str(result)

    if isinstance(result, dict):
        return ", ".join(f"${v} = {_safe_latex(result[v])}$" for v in target_vars if v in result)

    if isinstance(result, list) and len(target_vars) == 1:
        v = target_vars[0]
        return " | ".join(f"Solution {i}: ${v} = {_safe_latex(val)}$" for i, val in enumerate(result, 1))

    if isinstance(result, list) and result and isinstance(result[0], tuple):
        solution_parts = []
        for solution_index, values in enumerate(result, start=1):
            assignments = []
            for var_index, value in enumerate(values):
                if var_index < len(target_vars):
                    assignments.append(f"${target_vars[var_index]} = {_safe_latex(value)}$")
            solution_parts.append(f"Solution {solution_index}: {', '.join(assignments)}")
        return " | ".join(solution_parts)

    return _expr_text(result)

def _format_steps(operation, sympy_equations, target_vars, result):
    steps = []
    steps.append("Step 1: Parsed input")

    if operation == "derive":
        expression = sympy_equations[0].lhs
        variable = target_vars[0]
        steps.append(f"  Expression: ${_safe_latex(expression)}$")
        steps.append(f"  Differentiate with respect to: {variable}")
        steps.append("Step 2: Apply derivative")
        steps.append(f"  $\\frac{{d}}{{d{variable}}} {_safe_latex(expression)}$")
        steps.append("Step 3: Derivative")
        steps.append(f"  ${_safe_latex(result)}$")
        return "\n".join(steps)

    if operation in ["solve", "solve_system"]:
        for index, equation in enumerate(sympy_equations, start=1):
            steps.append(f"  Equation {index}: ${_safe_latex(equation.lhs)} = {_safe_latex(equation.rhs)}$")
        steps.append(f"  Target variables: {[str(variable) for variable in target_vars]}")

        steps.append("Step 2: Convert to standard form (lhs - rhs = 0)")
        for index, equation in enumerate(sympy_equations, start=1):
            standard_form = sp.simplify(equation.lhs - equation.rhs)
            steps.append(f"  Eq{index}: ${_safe_latex(standard_form)} = 0$")

        steps.append("Step 3: Solve the system")
        
        steps.append("Step 4: Final answer")
        if isinstance(result, dict):
            for variable in target_vars:
                if variable in result:
                    steps.append(f"  ${variable} = {_safe_latex(result[variable])}$")
        elif isinstance(result, list):
            if result and isinstance(result[0], dict):
                for solution_index, solution in enumerate(result, start=1):
                    pieces = []
                    for variable in target_vars:
                        if variable in solution:
                            pieces.append(f"{variable} = {_safe_latex(solution[variable])}")
                    steps.append(f"  Solution {solution_index}: {', '.join(pieces)}")
            else:
                if len(target_vars) == 1:
                    variable = target_vars[0]
                    for solution_index, value in enumerate(result, start=1):
                        steps.append(f"  Solution {solution_index}: ${variable} = {_safe_latex(value)}$")
                else:
                    steps.append(f"  Solutions: {[_safe_latex(v) for v in result]}")
        else:
            steps.append(f"  Solution: ${_safe_latex(result)}$")

    elif operation == "integrate":
        expression = sympy_equations[0].lhs
        variable = target_vars[0]
        steps.append(f"  Expression: ${_safe_latex(expression)}$")
        steps.append(f"  Variable of integration: {variable}")
        steps.append("Step 2: Apply integral")
        steps.append(f"  $\\int {_safe_latex(expression)} \\, d{variable}$")
        steps.append("Step 3: Final antiderivative")
        steps.append(f"  ${_safe_latex(result)} + C$")

    return "\n".join(steps)

def _is_linear_equation(equation, variables):
    expression = sp.expand(equation.lhs - equation.rhs)
    try:
        poly = sp.Poly(expression, *variables)
    except (ValueError, TypeError):
        return False
    return poly.total_degree() <= 1

def _format_student_linear_steps(sympy_equations, target_vars, result):
    if not sympy_equations or not target_vars:
        return None

    if not all(_is_linear_equation(equation, target_vars) for equation in sympy_equations):
        return None

    standard_forms = [sp.expand(eq.lhs - eq.rhs) for eq in sympy_equations]
    steps = ["Step 1: Rewrite in standard form"]
    for index, expression in enumerate(standard_forms, start=1):
        steps.append(f"  Eq{index}: ${_safe_latex(expression)} = 0$")

    if len(sympy_equations) == 1 and len(target_vars) == 1:
        variable = target_vars[0]
        expression = standard_forms[0]
        coefficient = sp.expand(expression).coeff(variable)
        constant = sp.simplify(expression - coefficient * variable)
        if coefficient == 0:
            return None
        steps.append("Step 2: Isolate the variable")
        steps.append(f"  ${_safe_latex(coefficient)} \\cdot {variable} + ({_safe_latex(constant)}) = 0$")
        steps.append(f"  ${_safe_latex(coefficient)} \\cdot {variable} = -{_safe_latex(constant)}$")
        isolated = sp.simplify(-constant / coefficient)
        steps.append(f"  ${variable} = {_safe_latex(isolated)}$")
        steps.append("Step 3: Final answer")
        if isinstance(result, list):
            for solution_index, value in enumerate(result, start=1):
                steps.append(f"  Solution {solution_index}: ${variable} = {_safe_latex(value)}$")
        else:
            steps.append(f"  ${variable} = {_safe_latex(result)}$")
        return "\n".join(steps)

    if len(sympy_equations) == 2 and len(target_vars) == 2:
        try:
            matrix_a, matrix_b = sp.linear_eq_to_matrix(sympy_equations, target_vars)
        except Exception:
            return None

        a11, a12 = matrix_a[0, 0], matrix_a[0, 1]
        a21, a22 = matrix_a[1, 0], matrix_a[1, 1]
        c1, c2 = matrix_b[0, 0], matrix_b[1, 0]
        x_var, y_var = target_vars[0], target_vars[1]

        steps.append("Step 2: Convert to coefficient form")
        steps.append(f"  Eq1: $({_safe_latex(a11)}){x_var} + ({_safe_latex(a12)}){y_var} = {_safe_latex(c1)}$")
        steps.append(f"  Eq2: $({_safe_latex(a21)}){x_var} + ({_safe_latex(a22)}){y_var} = {_safe_latex(c2)}$")

        determinant = sp.simplify(a11 * a22 - a21 * a12)
        if determinant == 0:
            return None

        steps.append("Step 3: Eliminate one variable using Cramer's rule")
        steps.append(f"  Determinant = ${_safe_latex(a11)} \\cdot {_safe_latex(a22)} - {_safe_latex(a21)} \\cdot {_safe_latex(a12)} = {_safe_latex(determinant)}$")
        x_num = sp.simplify(c1 * a22 - c2 * a12)
        steps.append(f"  ${x_var} = \\frac{{{_safe_latex(x_num)}}}{{{_safe_latex(determinant)}}}$")
        x_value = sp.simplify(x_num / determinant)
        steps.append(f"  ${x_var} = {_safe_latex(x_value)}$")

        steps.append("Step 4: Substitute back to get the second variable")
        y_num = sp.simplify(c1 - a11 * x_value)
        if a12 != 0:
            y_value = sp.simplify(y_num / a12)
            steps.append(f"  From Eq1: $({_safe_latex(a11)}) \\cdot ({_safe_latex(x_value)}) + ({_safe_latex(a12)}){y_var} = {_safe_latex(c1)}$")
        elif a22 != 0:
            y_num = sp.simplify(c2 - a21 * x_value)
            y_value = sp.simplify(y_num / a22)
            steps.append(f"  From Eq2: $({_safe_latex(a21)}) \\cdot ({_safe_latex(x_value)}) + ({_safe_latex(a22)}){y_var} = {_safe_latex(c2)}$")
        else:
            return None
        steps.append(f"  ${y_var} = {_safe_latex(y_value)}$")

        steps.append("Step 5: Final answer")
        if isinstance(result, dict):
            steps.append(f"  ${x_var} = {_safe_latex(result.get(x_var, x_value))}$")
            steps.append(f"  ${y_var} = {_safe_latex(result.get(y_var, y_value))}$")
        elif isinstance(result, list) and result and isinstance(result[0], dict):
            for solution_index, solution in enumerate(result, start=1):
                parts = []
                for variable in target_vars:
                    if variable in solution:
                        parts.append(f"{variable} = {_safe_latex(solution[variable])}")
                steps.append(f"  Solution {solution_index}: {', '.join(parts)}")
        else:
            steps.append(f"  ${x_var} = {_safe_latex(x_value)}$")
            steps.append(f"  ${y_var} = {_safe_latex(y_value)}$")

        return "\n".join(steps)

    return None

def _format_dsolve_steps(diff_eq, solution, dep_var_name):
    """Format steps for solving differential equations in a student-friendly way."""
    steps = []
    
    # Step 1: Identify and classify the ODE
    steps.append("Step 1: Classify the Differential Equation")
    lhs = diff_eq.lhs
    rhs = diff_eq.rhs
    
    # Analyze the equation to determine its type
    # In SymPy, Derivative(f, (x, n)) means nth derivative
    max_order = 0
    
    for arg in sp.preorder_traversal(lhs):
        if isinstance(arg, sp.Derivative):
            # Extract order from the derivative structure
            # Format: Derivative.args[1] is a Tuple (x, order)
            if len(arg.args) >= 2:
                try:
                    deriv_info = arg.args[1]
                    # Access like a sequence - it's a sympy Tuple
                    if len(deriv_info) >= 2:
                        order = int(deriv_info[1])
                        max_order = max(max_order, order)
                    else:
                        max_order = max(max_order, 1)
                except:
                    max_order = max(max_order, 1)
    
    # If no derivatives found explicitly, assume first order
    if max_order == 0:
        max_order = 1
    
    # Classify the ODE order (ordinal number string)
    order_names = {1: "1st-order", 2: "2nd-order", 3: "3rd-order"}
    ode_order = order_names.get(max_order, f"{max_order}th-order") + " ODE"
    
    # Check if it's linear by testing if nonlinear terms exist
    is_linear = True
    try:
        test_expr = lhs - rhs
        y_sym = sp.Symbol(dep_var_name)
        test1 = test_expr.subs(y_sym, 2*y_sym)
        test2 = 2 * test_expr
        is_linear = sp.simplify(test1 - test2) == 0
    except:
        is_linear = True  # Assume linear if test fails
    
    linear_status = "Linear" if is_linear else "Nonlinear"
    
    steps.append(f"  Type: {linear_status} {ode_order}")
    # Display equation in LaTeX format
    eq_latex = _safe_latex(lhs - rhs) if rhs != 0 else _safe_latex(lhs)
    steps.append(f"  Standard form: ${eq_latex} = 0$")
    
    # Step 2: Explain what we need to find
    steps.append("Step 2: What We're Looking For")
    steps.append(f"  We need to find $y(x)$ that satisfies the equation above.")
    steps.append(f"  This is called the 'general solution' because it contains arbitrary constants.")
    
    # Step 3: Solution method
    steps.append("Step 3: Solution Method")
    steps.append(f"  For this type of ODE, we use standard techniques:")
    if max_order == 1:
        steps.append(f"  - Check if the equation is separable (can separate $x$ and $y$)")
        steps.append(f"  - Or solve using integrating factor method")
    elif max_order == 2:
        steps.append(f"  - Form the characteristic equation")
        steps.append(f"  - Find the characteristic roots (can be real, complex, or repeated)")
        steps.append(f"  - Build the solution based on root types")
    elif max_order == 3:
        steps.append(f"  - Form the characteristic equation (cubic)")
        steps.append(f"  - Find three characteristic roots")
    else:
        steps.append(f"  - Use appropriate ODE solving techniques")
    steps.append(f"  SymPy automatically applies the best technique.")
    
    # Step 4: General solution
    steps.append("Step 4: General Solution")
    solution_latex = _safe_latex(solution.rhs)
    steps.append(f"  $y(x) = {solution_latex}$")
    
    # Step 5: Interpret the arbitrary constants
    steps.append("Step 5: Understanding the Arbitrary Constants")
    solution_rhs = solution.rhs
    constants = sorted([s for s in solution_rhs.free_symbols if 'C' in str(s)], key=str)
    
    if constants:
        steps.append(f"  This general solution contains {len(constants)} arbitrary constant(s):")
        for idx, const in enumerate(constants, start=1):
            steps.append(f"  - ${const}$: Will be determined by initial/boundary conditions")
        steps.append(f"")
        steps.append(f"  Why arbitrary constants? Each represents a degree of freedom.")
        ode_order_name = order_names.get(max_order, f"{max_order}th-order")
        steps.append(f"  A {ode_order_name} ODE needs {max_order} condition(s)")
        steps.append(f"  to uniquely determine all constants.")
    
    # Step 6: How to use this solution
    steps.append("Step 6: Using This Solution - Finding a Particular Solution")
    steps.append(f"  The general solution above represents INFINITELY many functions.")
    steps.append(f"  To find ONE specific solution, apply initial/boundary conditions:")
    if max_order == 1:
        steps.append(f"  Example: Given $y(0) = 1$")
        steps.append(f"           Substitute to find $C_1$")
    elif max_order == 2:
        steps.append(f"  Example: Given $y(0) = 1$ and $y'(0) = 0$")
        steps.append(f"           Substitute to get system of equations")
        steps.append(f"           Solve to find both $C_1$ and $C_2$")
    
    return "\n".join(steps)


def _format_matrix_steps(matrix, operation, result):
    """Format steps for matrix operations."""
    steps = []
    steps.append("Step 1: Parse and Display Matrix")
    steps.append("")
    steps.append("Input Matrix:")
    # Display matrix in LaTeX format for UI, text for terminal
    matrix_latex = _matrix_to_latex(matrix)
    steps.append(f"LATEX_MATRIX:{matrix_latex}")
    
    steps.append("")
    steps.append(f"Step 2: Apply {operation.title()} Operation")
    
    if operation == "determinant":
        steps.append("  The determinant is a scalar value representing the matrix's 'volume scaling factor'.")
        steps.append("  For a 2×2 matrix: det([[a,b],[c,d]]) = ad - bc")
        steps.append("  For larger matrices: Use cofactor expansion or row reduction.")
        
    elif operation == "inverse":
        steps.append("  The inverse matrix A⁻¹ satisfies: A × A⁻¹ = I (identity matrix)")
        steps.append("  Method: Gauss-Jordan elimination or adjugate formula.")
        steps.append("  Note: Inverse exists only if determinant ≠ 0.")
        
    elif operation == "eigenvalues":
        steps.append("  Eigenvalues λ satisfy: det(A - λI) = 0 (characteristic equation)")
        steps.append("  These are scalars that stretch/compress space during linear transformation.")
        
    elif operation == "eigenvectors":
        steps.append("  Eigenvectors v satisfy: Av = λv")
        steps.append("  For each eigenvalue λ, solve (A - λI)v = 0 to find eigenvector(s).")
        
    elif operation == "transpose":
        steps.append("  Transpose flips the matrix over its main diagonal.")
        steps.append("  Rows become columns and columns become rows: Aᵀ[i,j] = A[j,i]")
        
    elif operation == "rref":
        steps.append("  Row Reduced Echelon Form (RREF): Simplifies a matrix to identify its rank and solve systems.")
        steps.append("  ⚠️  NOTE: RREF is NOT the same as finding the matrix inverse!")
        steps.append("  Process: Use Gaussian elimination to get leading 1's with zeros above and below.")
        steps.append("  Use: Solving systems of equations, finding rank, identifying pivot columns.")
        steps.append("  For the inverse, use the 'inverse' operation instead.")
        
    elif operation == "rank":
        steps.append("  Rank = number of linearly independent rows (or columns).")
        steps.append("  Computed by counting non-zero rows in the RREF of the matrix.")
        
    elif operation == "trace":
        steps.append("  Trace = sum of all diagonal elements.")
        steps.append("  Formula: tr(A) = a₁₁ + a₂₂ + ... + aₙₙ")
    
    steps.append("")
    steps.append(f"Step 3: Computation Complete")
    steps.append(f"  Result computed using SymPy's matrix algorithms.")
    
    return "\n".join(steps)


def _format_limit_steps(expression, variable, approach_value, direction, result):
    """Format steps for limit calculations."""
    steps = []
    steps.append("Step 1: Identify Limit Problem")
    steps.append(f"  Expression: ${_safe_latex(expression)}$")
    steps.append(f"  Variable: {variable}")
    steps.append(f"  Approaching: ${_safe_latex(approach_value)}$")
    
    if direction == "+":
        steps.append(f"  Direction: From the right (${variable} \\to {approach_value}^+$)")
    elif direction == "-":
        steps.append(f"  Direction: From the left (${variable} \\to {approach_value}^-$)")
    else:
        steps.append(f"  Direction: Two-sided limit")
    
    steps.append("\nStep 2: Evaluate Limit")
    steps.append("  Method: Direct substitution, L'Hôpital's rule, or algebraic manipulation")
    
    # Try direct substitution first
    try:
        direct = expression.subs(variable, approach_value)
        steps.append(f"  Direct substitution: ${sp.latex(direct)}$")
        if direct.has(sp.zoo) or direct.has(sp.nan):
            steps.append("  Result is indeterminate - using advanced techniques")
    except:
        steps.append("  Direct substitution: indeterminate form")
    
    steps.append(f"\nStep 3: Final Result")
    steps.append(f"  $\\lim_{{{variable} \\to {approach_value}}} {sp.latex(expression)} = {sp.latex(result)}$")
    
    return "\n".join(steps)


def _format_series_steps(expression, variable, point, order, result):
    """Format steps for Taylor/Maclaurin series expansion."""
    steps = []
    steps.append("Step 1: Identify Series Expansion")
    steps.append(f"  Expression: ${_safe_latex(expression)}$")
    steps.append(f"  Variable: {variable}")
    steps.append(f"  Expansion point (a): ${_safe_latex(point)}$")
    steps.append(f"  Order: {order} terms")
    
    if point == 0:
        steps.append("\n  This is a Maclaurin series (Taylor series at $x=0$)")
    else:
        steps.append(f"\n  This is a Taylor series centered at $x={_safe_latex(point)}$")
    
    steps.append("\nStep 2: Apply Taylor Formula")
    steps.append(f"  $f(x) = f(a) + f'(a)(x-a) + \\frac{{f''(a)}}{{2!}}(x-a)^2 + \\frac{{f'''(a)}}{{3!}}(x-a)^3 + \\ldots$")
    steps.append(f"  Compute derivatives at $x={_safe_latex(point)}$ up to order {order}")
    
    steps.append(f"\nStep 3: Series Expansion")
    steps.append(f"  ${_safe_latex(result)} + O({variable}^{{{order+1}}})$")
    
    return "\n".join(steps)


def _format_partial_derivative_steps(expression, variables, result):
    """Format steps for partial derivatives."""
    steps = []
    steps.append("Step 1: Identify Multivariable Function")
    steps.append(f"  Expression: ${_safe_latex(expression)}$")
    steps.append(f"  Variables: {', '.join(str(v) for v in variables)}")
    
    steps.append("\nStep 2: Apply Partial Differentiation")
    steps.append(f"  Differentiating with respect to: {' then '.join(str(v) for v in variables)}")
    steps.append("  Treat other variables as constants at each step")
    
    # Show intermediate steps for each variable
    temp_expr = expression
    for i, var in enumerate(variables, 1):
        temp_expr = sp.diff(temp_expr, var)
        steps.append(f"\n  Step 2.{i}: $\\frac{{\\partial}}{{\\partial {var}}}$")
        steps.append(f"  Result: ${_safe_latex(temp_expr)}$")
    
    steps.append(f"\nStep 3: Final Partial Derivative")
    steps.append(f"  ${_safe_latex(result)}$")
    
    return "\n".join(steps)


def _solve_from_ai_data(ai_data):
    # 1. Dynamically build a list of all equations
    sympy_equations = []
    for eq_data in ai_data["equations"]:
        # Wrap the JSON values in str() to guarantee they are strings
        lhs_expr = parse_expr(str(eq_data["lhs"]))
        rhs_expr = parse_expr(str(eq_data["rhs"]))
        sympy_equations.append(sp.Eq(lhs_expr, rhs_expr))

    # 2. Dynamically build a list of all target variables
    target_vars = [sp.Symbol(var) for var in ai_data["target_variables"]]

    # 3. Route the logic
    if ai_data["operation"] in ["solve", "solve_system"]:
        # sp.solve() natively handles both single equations and lists of equations!
        solutions = sp.solve(sympy_equations, target_vars)
        step_text = _format_student_linear_steps(sympy_equations, target_vars, solutions)
        if step_text is None:
            step_text = _format_steps(ai_data["operation"], sympy_equations, target_vars, solutions)
        return f"{step_text}\n\nFinal Result: {_final_text(ai_data['operation'], solutions, target_vars)}"

    if ai_data["operation"] == "derive":
        derivative = sp.diff(sympy_equations[0].lhs, target_vars[0])
        step_text = _format_steps(ai_data["operation"], sympy_equations, target_vars, derivative)
        
        # Add graphable equation for UI
        variable_name = str(target_vars[0])
        original_expr = _expr_text(sympy_equations[0].lhs)
        derivative_expr = _expr_text(derivative)
        
        # Create graphable equations entry with better formatting
        final_result = f"{_final_text(ai_data['operation'], derivative, target_vars)}"
        
        graphable_section = "\n\nGraphable Functions:"
        graphable_section += f"\n- Original: $y = {_safe_latex(sympy_equations[0].lhs)}$"
        graphable_section += f"\n- Derivative: $y = {_safe_latex(derivative)}$"
        
        return f"{step_text}\n\nFinal Result:\n{final_result}{graphable_section}"

    if ai_data["operation"] == "integrate":
        integral = sp.integrate(sympy_equations[0].lhs, target_vars[0])
        step_text = _format_steps(ai_data["operation"], sympy_equations, target_vars, integral)
        
        # Add graphable equation for UI
        variable_name = str(target_vars[0])
        original_expr = _expr_text(sympy_equations[0].lhs)
        integral_expr = _expr_text(integral)
        
        # Create graphable equations entry with better formatting
        final_result = f"{_final_text(ai_data['operation'], integral, target_vars)} + C"
        
        graphable_section = "\n\nGraphable Functions:"
        graphable_section += f"\n- Original: $y = {_safe_latex(sympy_equations[0].lhs)}$"
        graphable_section += f"\n- Integral: $y = {_safe_latex(integral)} + C$"
        
        return f"{step_text}\n\nFinal Result:\n{final_result}{graphable_section}"

    if ai_data["operation"] == "dsolve":
        # For differential equations, parse with Function for the dependent variable
        dependent_var_name = ai_data["target_variables"][0]
        independent_var_name = "x"  # Assume x is independent variable unless specified
        
        # Create function and symbol
        dependent_var = sp.Function(dependent_var_name)
        independent_var = sp.Symbol(independent_var_name)
        
        # Parse the differential equation
        try:
            lhs_expr = parse_expr(str(ai_data["equations"][0]["lhs"]), local_dict={
                'Derivative': lambda *args: sp.Derivative(*args),
                dependent_var_name: dependent_var,
                'x': independent_var
            })
            rhs_expr = parse_expr(str(ai_data["equations"][0]["rhs"]), local_dict={
                'Derivative': lambda *args: sp.Derivative(*args),
                dependent_var_name: dependent_var,
                'x': independent_var
            })
        except Exception:
            # Fallback: try to parse with basic parsing
            try:
                lhs_str = str(ai_data["equations"][0]["lhs"]).replace(dependent_var_name, f"{dependent_var_name}(x)")
                rhs_str = str(ai_data["equations"][0]["rhs"]).replace(dependent_var_name, f"{dependent_var_name}(x)")
                lhs_expr = parse_expr(lhs_str, local_dict={'Derivative': sp.Derivative, dependent_var_name: dependent_var})
                rhs_expr = parse_expr(rhs_str, local_dict={'Derivative': sp.Derivative, dependent_var_name: dependent_var})
            except Exception as e:
                return f"Error parsing differential equation: {e}"
        
        diff_eq = sp.Eq(lhs_expr, rhs_expr)
        
        # Solve the differential equation
        try:
            solution = sp.dsolve(diff_eq, dependent_var(independent_var))
            step_text = _format_dsolve_steps(diff_eq, solution, dependent_var_name)
            return f"{step_text}\n\nFinal Result: {solution}"
        except Exception as e:
            return f"Error solving differential equation: {e}"
    
    if ai_data["operation"] == "matrix_ops":
        # Parse matrix from lhs
        try:
            matrix = parse_expr(str(ai_data["equations"][0]["lhs"]))
            operation = ai_data.get("matrix_operation")
            
            # Handle missing or invalid operation
            if not operation or operation == "none" or operation == "null":
                return ("Error: Matrix operation not specified. Please specify what to do with the matrix.\n"
                       "Available operations: determinant, inverse, eigenvalues, eigenvectors, transpose, rref, rank, trace.\n"
                       "Example: 'Find the determinant of [[1,2],[3,4]]'")
            
            # Validate operation
            valid_operations = ["determinant", "inverse", "eigenvalues", "eigenvectors", "transpose", "rref", "rank", "trace"]
            if operation not in valid_operations:
                return f"Error: Matrix operation '{operation}' not recognized.\nValid operations: {', '.join(valid_operations)}"
            
            if operation == "determinant":
                result = matrix.det()
                step_text = _format_matrix_steps(matrix, operation, result)
                return f"{step_text}\n\nFinal Result: Determinant = {_expr_text(result)}"
                
            elif operation == "inverse":
                result = matrix.inv()
                step_text = _format_matrix_steps(matrix, operation, result)
                result_latex = _matrix_to_latex(result)
                return f"{step_text}\n\nFinal Result: Inverse Matrix =\nLATEX_MATRIX:{result_latex}"
                
            elif operation == "eigenvalues":
                result = matrix.eigenvals()
                step_text = _format_matrix_steps(matrix, operation, result)
                eigenval_text = ", ".join(f"λ{i} = {_expr_text(val)} (multiplicity {mult})" 
                                         for i, (val, mult) in enumerate(result.items(), 1))
                return f"{step_text}\n\nFinal Result:\nEigenvalues: {eigenval_text}"
                
            elif operation == "eigenvectors":
                result = matrix.eigenvects()
                step_text = _format_matrix_steps(matrix, operation, result)
                eigenvec_parts = []
                for val, mult, vecs in result:
                    eigenvec_parts.append(f"\nEigenvalue λ = {_expr_text(val)} (multiplicity {mult})")
                    eigenvec_parts.append("Eigenvector(s):")
                    for vec in vecs:
                        vec_latex = _matrix_to_latex(vec)
                        eigenvec_parts.append(f"LATEX_MATRIX:{vec_latex}")
                eigenvec_text = "\n".join(eigenvec_parts)
                return f"{step_text}\n\nFinal Result:{eigenvec_text}"
                
            elif operation == "transpose":
                result = matrix.T
                step_text = _format_matrix_steps(matrix, operation, result)
                result_latex = _matrix_to_latex(result)
                return f"{step_text}\n\nFinal Result: Transpose =\nLATEX_MATRIX:{result_latex}"
                
            elif operation == "rref":
                result, pivot_cols = matrix.rref()
                step_text = _format_matrix_steps(matrix, operation, result)
                result_latex = _matrix_to_latex(result)
                
                # Add helpful note
                note = "\n\n⚠️  Note: This is the RREF (Row Reduced Echelon Form), NOT the inverse!"
                note += "\nTo find the inverse, use: 'Calculate the inverse of [[...]]'"
                
                return f"{step_text}\n\nPivot columns: {pivot_cols}\n\nFinal Result: RREF =\nLATEX_MATRIX:{result_latex}{note}"
                
            elif operation == "rank":
                result = matrix.rank()
                step_text = _format_matrix_steps(matrix, operation, result)
                return f"{step_text}\n\nFinal Result: Rank = {result}"
                
            elif operation == "trace":
                result = matrix.trace()
                step_text = _format_matrix_steps(matrix, operation, result)
                return f"{step_text}\n\nFinal Result: Trace = {_expr_text(result)}"
            else:
                return f"Matrix operation '{operation}' not recognized"
                
        except Exception as e:
            return f"Error in matrix operation: {e}"
    
    if ai_data["operation"] == "limit":
        try:
            expression = parse_expr(str(ai_data["equations"][0]["lhs"]))
            variable = sp.Symbol(ai_data["target_variables"][0])
            approach_value = parse_expr(str(ai_data["equations"][0]["rhs"]))
            
            # Check for direction parameter
            extra_params = ai_data.get("extra_params", {})
            direction = extra_params.get("direction", "+-")
            
            if direction == "+":
                result = sp.limit(expression, variable, approach_value, '+')
            elif direction == "-":
                result = sp.limit(expression, variable, approach_value, '-')
            else:
                result = sp.limit(expression, variable, approach_value)
            
            step_text = _format_limit_steps(expression, variable, approach_value, direction, result)
            return f"{step_text}\n\nFinal Result: {_expr_text(result)}"
            
        except Exception as e:
            return f"Error calculating limit: {e}"
    
    if ai_data["operation"] == "series":
        try:
            expression = parse_expr(str(ai_data["equations"][0]["lhs"]))
            variable = sp.Symbol(ai_data["target_variables"][0])
            
            extra_params = ai_data.get("extra_params", {})
            point = int(extra_params.get("point", 0))
            order = int(extra_params.get("order", 6))
            
            result = sp.series(expression, variable, point, order).removeO()
            step_text = _format_series_steps(expression, variable, point, order, result)
            return f"{step_text}\n\nFinal Result: {_expr_text(result)}"
            
        except Exception as e:
            return f"Error computing series: {e}"
    
    if ai_data["operation"] == "simplify":
        try:
            expression = parse_expr(str(ai_data["equations"][0]["lhs"]))
            result = sp.simplify(expression)
            
            steps = []
            steps.append("Step 1: Original Expression")
            steps.append(f"  {_expr_text(expression)}")
            steps.append("\nStep 2: Apply Simplification")
            steps.append("  Using algebraic rules, trigonometric identities, and factoring")
            steps.append("\nStep 3: Simplified Result")
            steps.append(f"  {_expr_text(result)}")
            
            return f"{chr(10).join(steps)}\n\nFinal Result: {_expr_text(result)}"
            
        except Exception as e:
            return f"Error simplifying expression: {e}"
    
    if ai_data["operation"] == "partial_derivative":
        try:
            expression = parse_expr(str(ai_data["equations"][0]["lhs"]))
            variables = [sp.Symbol(var) for var in ai_data["target_variables"]]
            
            # Apply partial derivatives in order
            result = expression
            for var in variables:
                result = sp.diff(result, var)
            
            step_text = _format_partial_derivative_steps(expression, variables, result)
            return f"{step_text}\n\nFinal Result: {_expr_text(result)}"
            
        except Exception as e:
            return f"Error computing partial derivative: {e}"

    return "Operation not fully implemented in backend yet."


def level_2_solver(user_input, show_translation=False, return_translation=False):
    try:
        # Phase 1: The AI Translator
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ],
            response_format={"type": "json_object"}, # Forces pure JSON output
            temperature=0.1
        )
        
        # Parse the AI's JSON string into a Python dictionary
        content = response.choices[0].message.content
        if content is None:
            return "Error: API returned no content"
        ai_data = json.loads(content)
        
        if show_translation:
            print(f"--- AI Translation --- \n{json.dumps(ai_data, indent=2)}\n")
        
        solved_text = _solve_from_ai_data(ai_data)
        if return_translation:
            return solved_text, ai_data
        return solved_text

    except Exception as e:
        if return_translation:
            return f"System Error: {e}", None
        return f"System Error: {e}"

if __name__ == "__main__":
    # Test basic operations
    print("=== System of Equations ===")
    print(level_2_solver("Solve 2x + y = 10 and x - y = 2", show_translation=True))
    print("\n" + "="*60 + "\n")
    
    # Test derivative
    print("=== Derivative ===")
    print(level_2_solver("what is the derivative of e^-2x sin(3x) with respect to x", show_translation=True))
    print("\n" + "="*60 + "\n")
    
    # Test differential equation
    print("=== Differential Equation ===")
    print(level_2_solver("Solve the differential equation dy/dx = 2*x with respect to y", show_translation=True))
    print("\n" + "="*60 + "\n")
    
    # Test matrix operations
    print("=== Matrix Determinant ===")
    print(level_2_solver("Find the determinant of [[1, 2], [3, 4]]", show_translation=True))
    print("\n" + "="*60 + "\n")
    
    print("=== Matrix Inverse ===")
    print(level_2_solver("Find the inverse of the matrix [[2, 1], [1, 3]]", show_translation=True))
    print("\n" + "="*60 + "\n")
    
    # Test limit
    print("=== Limit ===")
    print(level_2_solver("Find the limit of (x^2 - 1)/(x - 1) as x approaches 1", show_translation=True))
    print("\n" + "="*60 + "\n")
    
    # Test series
    print("=== Taylor Series ===")
    print(level_2_solver("Find the Taylor series of e^x at x=0 up to order 5", show_translation=True))
    print("\n" + "="*60 + "\n")
    
    # Test simplification
    print("=== Simplify ===")
    print(level_2_solver("Simplify (x^2 - 1)/(x - 1)", show_translation=True))
    print("\n" + "="*60 + "\n")
    
    # Test partial derivative
    print("=== Partial Derivative ===")
    print(level_2_solver("Find the partial derivative of x^2*y + y^3 with respect to x and then y", show_translation=True))