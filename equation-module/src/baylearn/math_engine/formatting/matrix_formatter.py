"""Matrix-focused formatting helpers."""

from typing import Any

from .expression_formatter import expr_text
from .latex_utils import safe_latex


def matrix_to_latex(matrix: Any) -> str:
    """Convert matrix-like object to LaTeX.

    Args:
        matrix: SymPy Matrix or matrix-like object.

    Returns:
        LaTeX string.
    """
    if not hasattr(matrix, "rows") or not hasattr(matrix, "cols"):
        return safe_latex(matrix)
    return safe_latex(matrix)


def format_matrix_display(matrix: Any) -> str:
    """Render matrix as aligned plain-text block.

    Args:
        matrix: SymPy Matrix or matrix-like object.

    Returns:
        Pretty text matrix display.
    """
    if not hasattr(matrix, "rows") or not hasattr(matrix, "cols"):
        return str(matrix)

    rows = matrix.rows
    cols = matrix.cols
    matrix_data = []
    for i in range(rows):
        row = []
        for j in range(cols):
            row.append(expr_text(matrix[i, j]))
        matrix_data.append(row)

    col_widths = []
    for j in range(cols):
        col_widths.append(max(len(matrix_data[i][j]) for i in range(rows)))

    lines = []
    lines.append("┌" + " " * (sum(col_widths) + 3 * (cols - 1) + 2) + "┐")
    for i in range(rows):
        row_parts = []
        for j in range(cols):
            row_parts.append(matrix_data[i][j].rjust(col_widths[j]))
        lines.append("│ " + "   ".join(row_parts) + " │")
    lines.append("└" + " " * (sum(col_widths) + 3 * (cols - 1) + 2) + "┘")
    return "\n".join(lines)
