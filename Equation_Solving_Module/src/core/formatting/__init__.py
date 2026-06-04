"""Expose presentation and formatting builders safely."""
from .latex import safe_latex, expr_to_clean_text, matrix_to_latex, format_matrix_text_grid
from .steps import (
    format_base_steps,
    format_student_linear_steps,
    format_dsolve_steps,
    format_matrix_steps,
    format_limit_steps,
    format_series_steps,
    format_partial_derivative_steps,
    build_final_text_block
)