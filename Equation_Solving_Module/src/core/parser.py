import sympy as sp
from sympy.parsing.sympy_parser import (
    parse_expr,
    standard_transformations,
    implicit_multiplication_application,
    convert_xor,
)


def solve_math_string(user_input: str) -> str:
    """
    Parse and solve a simple math equation from a string.
    this function is the level one solver that works on taking the equation and solving it directly
    
    Args:
        user_input: Mathematical equation as string (e.g., "2y - 4 = 14")
        
    Returns:
        string representation of the solution
    """
    #lexical analysis and cleanning of the input
    clean_input = user_input.replace(" ", "")
    
    if "=" not in clean_input:
        return "Error: Equation must contain an '=' sign."
        
    lhs_string, rhs_string = clean_input.split("=")
    
    # parsing and transforming (The Compiler step) to handle natural math lang
    transformations = standard_transformations + (
        implicit_multiplication_application,
        convert_xor,
    )
    
    try:
        # Build the mathematical objects for both sides
        lhs_expr = parse_expr(lhs_string, transformations=transformations)
        rhs_expr = parse_expr(rhs_string, transformations=transformations)
        
        # semantic evaluation of the equations
        # save it a as sympy equation
        equation = sp.Eq(lhs_expr, rhs_expr)
        
        # detect the variable (e.g., 'x', 'y', 't')
        variables = equation.free_symbols
        if not variables:
            return "Error: No variables found in the equation"
            
        target_var = list(variables)[0]
        
        # Solve the equation
        solutions = sp.solve(equation, target_var)
        return f"{target_var} = {solutions}"
        
    except Exception as e:
        return f"Could not parse the mathematical syntax. Error: {e}"
