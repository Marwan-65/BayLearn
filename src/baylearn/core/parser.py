"""Basic equation parser for BayLearn."""

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
    
    Handles equations with equality signs and automatically detects the variable.
    
    Args:
        user_input: Mathematical equation as string (e.g., "2y - 4 = 14")
        
    Returns:
        String representation of the solution
    """
    # Phase 1: Lexical Analysis & Sanitization
    clean_input = user_input.replace(" ", "")
    
    if "=" not in clean_input:
        return "Error: Equation must contain an '=' sign."
        
    lhs_string, rhs_string = clean_input.split("=")
    
    # Phase 2: Parsing & Transformations (The Compiler step)
    # Combine standard rules with implicit multiplication and XOR conversion
    transformations = standard_transformations + (
        implicit_multiplication_application,
        convert_xor,
    )
    
    try:
        # Build the mathematical objects for both sides
        lhs_expr = parse_expr(lhs_string, transformations=transformations)
        rhs_expr = parse_expr(rhs_string, transformations=transformations)
        
        # Phase 3: Semantic Evaluation
        # Lock them into a strict SymPy Equation
        equation = sp.Eq(lhs_expr, rhs_expr)
        
        # Automatically detect the variable (e.g., 'x', 'y', 't')
        variables = equation.free_symbols
        if not variables:
            return "Error: No variables found in equation."
            
        target_var = list(variables)[0]
        
        # Solve the equation
        solutions = sp.solve(equation, target_var)
        return f"{target_var} = {solutions}"
        
    except Exception as e:
        return f"Could not parse the mathematical syntax. Error: {e}"
