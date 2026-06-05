"""Expose calculations blueprints mapping rules clearly."""
from .algebra import handle_solve, handle_simplify
from .calculus import handle_derive, handle_integrate, handle_limit, handle_series, handle_partial_derivative
from .differential import handle_dsolve
from .matrix import handle_matrix_ops