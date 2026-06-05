__version__ = "1.0.0"
__author__ = "SalmaNasser"
__email__ = "salma.naser1020@gmail.com"

from .core.solver import level_2_solver
from .core.parser import solve_math_string

__all__ = [
    "level_2_solver",
    "solve_math_string",
]
