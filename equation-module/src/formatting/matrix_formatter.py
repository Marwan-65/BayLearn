from typing import Any

from .expression_formatter import format_sympy_as_plain_text


def render_matrix_as_ascii_grid(matrix: Any) -> str:
    """format matrix as a plain text block
    Args:
        matrix: sympy matrix
    Returns:
        text matrix display
    """
    if not hasattr(matrix, "rows") or not hasattr(matrix, "cols"):
        return str(matrix)

    rows = matrix.rows
    cols = matrix.cols
    matrix_data = []
    for i in range(rows):
        row = []
        for j in range(cols):
            row.append(format_sympy_as_plain_text(matrix[i, j]))
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
