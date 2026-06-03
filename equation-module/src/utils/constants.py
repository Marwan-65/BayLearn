from typing import Dict, List

SUPPORTED_OPERATIONS: List[str] = [
    "solve",
    "solve_system",
    "derive",
    "integrate",
    "dsolve",
    "matrix_ops",
    "limit",
    "series",
    "simplify",
    "partial_derivative",
]

VALID_MATRIX_OPERATIONS: List[str] = [
    "determinant",
    "inverse",
    "eigenvalues",
    "eigenvectors",
    "transpose",
    "rref",
    "rank",
    "trace",
]

MAX_LATEX_LENGTH = 500
MAX_EXPRESSION_LENGTH = 60
DEFAULT_SERIES_ORDER = 6
DEFAULT_SERIES_POINT = 0

PROBLEMATIC_LATEX_PATTERNS: List[str] = [
    "\\left\\left",
    "\\right\\right",
    "{{{{",
    "}}}}",
    "}$",
    "$}",
]

ODE_ORDER_NAMES: Dict[int, str] = {
    1: "1st-order",
    2: "2nd-order",
    3: "3rd-order",
}
