import json
import os
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
2. Identify the core mathematical operation ('solve', 'solve_system', 'derive', 'integrate', or 'dsolve').
3. Format the equations as a list of objects. Each object must have a "lhs" and "rhs".
-ALL values for "lhs" and "rhs" MUST be formatted as strings, even if they are plain numbers. 
4. Identify the target variables and return them as a list of strings.
5. Output ONLY a valid JSON object with these exact keys: "operation", "equations", "target_variables". Do not include markdown.
6. For 'derive' and 'integrate' operations, place the actual mathematical expression STRICTLY in the "lhs" and set "rhs" to "0".
7. For 'dsolve' (differential equations), convert notation like dy/dx, y', or D(y, x) into SymPy's Derivative syntax:
   - Replace dy/dx with Derivative(y, x)
   - Replace y' with Derivative(y, x)
   - Replace D(y, x) with Derivative(y, x)
   - Place the differential equation in "lhs" format like "Derivative(y, x) - expression" or "Derivative(y, x) = expression" in "lhs = rhs" form
   - Target variable should be the function being solved for (e.g., "y" not "x")
NEVER use abstract function labels like "f(x)", "y", or "y(x)".
8. Translate standard mathematical functions into explicit SymPy syntax: 
- Euler's number 'e^x' MUST become 'exp(x)' (never 'e**x').
- Natural log 'ln(x)' MUST become 'log(x)'.
- Square root 'sqrt(x)' MUST become 'sqrt(x)'.
"""

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
    if operation in ["derive", "integrate"]:
        return _expr_text(result)

    if isinstance(result, dict):
        return ", ".join(f"{v} = {_expr_text(result[v])}" for v in target_vars if v in result)

    if isinstance(result, list) and len(target_vars) == 1:
        v = target_vars[0]
        return " | ".join(f"Solution {i}: {v} = {_expr_text(val)}" for i, val in enumerate(result, 1))

    if isinstance(result, list) and result and isinstance(result[0], tuple):
        solution_parts = []
        for solution_index, values in enumerate(result, start=1):
            assignments = []
            for var_index, value in enumerate(values):
                if var_index < len(target_vars):
                    assignments.append(f"{target_vars[var_index]} = {_expr_text(value)}")
            solution_parts.append(f"Solution {solution_index}: {', '.join(assignments)}")
        return " | ".join(solution_parts)

    return _expr_text(result)

def _format_steps(operation, sympy_equations, target_vars, result):
    steps = []
    steps.append("Step 1: Parsed input")

    if operation == "derive":
        expression = sympy_equations[0].lhs
        variable = target_vars[0]
        steps.append(f"  Expression: {_expr_text(expression)}")
        steps.append(f"  Differentiate w.r.t: {variable}")
        steps.append("Step 2: Apply derivative")
        steps.append(f"  d/d{variable}({_expr_text(expression)})")
        steps.append("Step 3: Derivative")
        steps.append(f"  {_expr_text(result)}")
        return "\n".join(steps)

    if operation in ["solve", "solve_system"]:
        for index, equation in enumerate(sympy_equations, start=1):
            steps.append(f"  Equation {index}: {_expr_text(equation.lhs)} = {_expr_text(equation.rhs)}")
        steps.append(f"  Target variables: {[str(variable) for variable in target_vars]}")

        steps.append("Step 2: Convert to standard form (lhs - rhs = 0)")
        for index, equation in enumerate(sympy_equations, start=1):
            standard_form = sp.simplify(equation.lhs - equation.rhs)
            steps.append(f"  Eq{index}: {_expr_text(standard_form)} = 0")

        steps.append("Step 3: Solve the system")
        steps.append(f"  Raw solution object: {result}")

        steps.append("Step 4: Final answer")
        if isinstance(result, dict):
            for variable in target_vars:
                if variable in result:
                    steps.append(f"  {variable} = {result[variable]}")
        elif isinstance(result, list):
            if result and isinstance(result[0], dict):
                for solution_index, solution in enumerate(result, start=1):
                    pieces = []
                    for variable in target_vars:
                        if variable in solution:
                            pieces.append(f"{variable} = {solution[variable]}")
                    steps.append(f"  Solution {solution_index}: {', '.join(pieces)}")
            else:
                if len(target_vars) == 1:
                    variable = target_vars[0]
                    for solution_index, value in enumerate(result, start=1):
                        steps.append(f"  Solution {solution_index}: {variable} = {value}")
                else:
                    steps.append(f"  Solutions: {result}")
        else:
            steps.append(f"  Solution: {result}")

    elif operation == "integrate":
        expression = sympy_equations[0].lhs
        variable = target_vars[0]
        steps.append(f"  Expression: {_expr_text(expression)}")
        steps.append(f"  Integrate with respect to: {variable}")
        steps.append("Step 2: Apply integral")
        steps.append(f"  Integral({_expr_text(expression)}, d{variable})")
        steps.append("Step 3: Final antiderivative")
        steps.append(f"  {_expr_text(result)} + C")

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
        steps.append(f"  Eq{index}: {_expr_text(expression)} = 0")

    if len(sympy_equations) == 1 and len(target_vars) == 1:
        variable = target_vars[0]
        expression = standard_forms[0]
        coefficient = sp.expand(expression).coeff(variable)
        constant = sp.simplify(expression - coefficient * variable)
        if coefficient == 0:
            return None
        steps.append("Step 2: Isolate the variable")
        steps.append(f"  {_expr_text(coefficient)}*{variable} + ({_expr_text(constant)}) = 0")
        steps.append(f"  {_expr_text(coefficient)}*{variable} = -({_expr_text(constant)})")
        isolated = sp.simplify(-constant / coefficient)
        steps.append(f"  {variable} = {_expr_text(isolated)}")
        steps.append("Step 3: Final answer")
        if isinstance(result, list):
            for solution_index, value in enumerate(result, start=1):
                steps.append(f"  Solution {solution_index}: {variable} = {value}")
        else:
            steps.append(f"  {variable} = {result}")
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
        steps.append(f"  Eq1: ({a11})*{x_var} + ({a12})*{y_var} = {c1}")
        steps.append(f"  Eq2: ({a21})*{x_var} + ({a22})*{y_var} = {c2}")

        determinant = sp.simplify(a11 * a22 - a21 * a12)
        if determinant == 0:
            return None

        steps.append("Step 3: Eliminate one variable")
        steps.append(f"  Multiply Eq1 by {a22}, multiply Eq2 by {a12}, then subtract")
        x_num = sp.simplify(c1 * a22 - c2 * a12)
        steps.append(f"  ({a11}*{a22} - {a21}*{a12})*{x_var} = {x_num}")
        x_value = sp.simplify(x_num / determinant)
        steps.append(f"  {x_var} = {_expr_text(x_value)}")

        steps.append("Step 4: Substitute back to get the second variable")
        y_num = sp.simplify(c1 - a11 * x_value)
        if a12 != 0:
            y_value = sp.simplify(y_num / a12)
            steps.append(f"  From Eq1: ({a11})*({x_value}) + ({a12})*{y_var} = {c1}")
        elif a22 != 0:
            y_num = sp.simplify(c2 - a21 * x_value)
            y_value = sp.simplify(y_num / a22)
            steps.append(f"  From Eq2: ({a21})*({x_value}) + ({a22})*{y_var} = {c2}")
        else:
            return None
        steps.append(f"  {y_var} = {_expr_text(y_value)}")

        steps.append("Step 5: Final answer")
        if isinstance(result, dict):
            steps.append(f"  {x_var} = {result.get(x_var, x_value)}")
            steps.append(f"  {y_var} = {result.get(y_var, y_value)}")
        elif isinstance(result, list) and result and isinstance(result[0], dict):
            for solution_index, solution in enumerate(result, start=1):
                parts = []
                for variable in target_vars:
                    if variable in solution:
                        parts.append(f"{variable} = {solution[variable]}")
                steps.append(f"  Solution {solution_index}: {', '.join(parts)}")
        else:
            steps.append(f"  {x_var} = {x_value}")
            steps.append(f"  {y_var} = {y_value}")

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
    # Display equation in a cleaner form  
    eq_str = str(lhs - rhs) if rhs != 0 else str(lhs)
    steps.append(f"  Standard form: {eq_str} = 0")
    
    # Step 2: Explain what we need to find
    steps.append("Step 2: What We're Looking For")
    steps.append(f"  We need to find y(x) that satisfies the equation above.")
    steps.append(f"  This is called the 'general solution' because it contains arbitrary constants.")
    
    # Step 3: Solution method
    steps.append("Step 3: Solution Method")
    steps.append(f"  For this type of ODE, we use standard techniques:")
    if max_order == 1:
        steps.append(f"  - Check if the equation is separable (can separate x and y)")
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
    solution_readable = _expr_to_readable_text(solution.rhs)
    steps.append(f"  y(x) = {solution_readable}")
    
    # Step 5: Interpret the arbitrary constants
    steps.append("Step 5: Understanding the Arbitrary Constants")
    solution_rhs = solution.rhs
    constants = sorted([s for s in solution_rhs.free_symbols if 'C' in str(s)], key=str)
    
    if constants:
        steps.append(f"  This general solution contains {len(constants)} arbitrary constant(s):")
        for idx, const in enumerate(constants, start=1):
            steps.append(f"  - {const}: Will be determined by initial/boundary conditions")
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
        steps.append(f"  Example: Given y(0) = 1")
        steps.append(f"           Substitute to find C1")
    elif max_order == 2:
        steps.append(f"  Example: Given y(0) = 1 and y'(0) = 0")
        steps.append(f"           Substitute to get system of equations")
        steps.append(f"           Solve to find both C1 and C2")
    
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
        return f"{step_text}\n\nFinal Result: {_final_text(ai_data['operation'], derivative, target_vars)}"

    if ai_data["operation"] == "integrate":
        integral = sp.integrate(sympy_equations[0].lhs, target_vars[0])
        step_text = _format_steps(ai_data["operation"], sympy_equations, target_vars, integral)
        return f"{step_text}\n\nFinal Result: {_final_text(ai_data['operation'], integral, target_vars)} + C"

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
    print(level_2_solver("Solve 2x + y = 10 and x - y = 2", show_translation=True))
    print(level_2_solver("what is the derivative of e^-2x sin(3x) with respect to x", show_translation=True))
    print(level_2_solver("Solve the differential equation dy/dx = 2*x with respect to y", show_translation=True))