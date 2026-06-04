import json
import sys
import os

# Ensure the root directory is in the path to import llm_client
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from Equation_module_model.llm_client import translate_math_input

# Import strategy routers cleanly from operations layer
from .operations import (
    handle_solve,
    handle_simplify,
    handle_derive,
    handle_integrate,
    handle_limit,
    handle_series,
    handle_partial_derivative,
    handle_dsolve,
    handle_matrix_ops
)

# dictionary to map each mode to it's handler function instead of relying on a long if-else chain
EXECUTION_ROUTERS = {
    "solve": handle_solve,
    "solve_system": handle_solve,
    "simplify": handle_simplify,
    "derive": handle_derive,
    "integrate": handle_integrate,
    "limit": handle_limit,
    "series": handle_series,
    "partial_derivative": handle_partial_derivative,
    "dsolve": handle_dsolve,        #differential equation solving 
    "matrix_ops": handle_matrix_ops,
}

def _dispatch_operation(ai_data: dict) -> str:
    """helper function to match each operation to it's routine"""
    operation = ai_data.get("operation")
    handler = EXECUTION_ROUTERS.get(operation)
    
    if not handler:
        return "Operation not fully implemented in backend yet."
        
    return handler(ai_data)


def level_2_solver(user_input: str, show_translation: bool = False, return_translation: bool = False):
    """
    advanced version of level one solver that handles the full pipeline instead of only solving the equation
    """
    try:
        # Phase 1: Translate messy human requests using the LLM engine
        ai_data = translate_math_input(user_input)
        
        if show_translation:
            print(f"--- AI Translation --- \n{json.dumps(ai_data, indent=2)}\n")
            
        # Phase 2: Compute results by routing the transaction
        solved_text = _dispatch_operation(ai_data)
        
        if return_translation:
            return solved_text, ai_data
        return solved_text

    except Exception as e:
        error_msg = f"System Error: {e}"
        return (error_msg, None) if return_translation else error_msg