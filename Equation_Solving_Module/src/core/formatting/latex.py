"""LaTeX sanitization, formatting, and validation utilities for math rendering."""

import re
import sympy as sp

def is_valid_latex(latex_str: str) -> bool:
    """
    Checks if a LaTeX string is structurally safe for frontend rendering.
    
    Verifies balanced brackets, length constraints, and isolates bad formatting patterns.
    """
    if not latex_str:
        return False
    
    # 1. Verify that curly braces are perfectly balanced
    if latex_str.count('{') != latex_str.count('}'):
        return False
    
    # 2. Verify that standard parentheses are balanced
    if latex_str.count('(') != latex_str.count(')'):
        return False
    
    # 3. Guard against problematic overlapping brackets and math blocks
    problematic_patterns = ['\\left\\left', '\\right\\right', '{{{{', '}}}}', '}$', '$}']
    if any(pattern in latex_str for pattern in problematic_patterns):
        return False
    
    # 4. Enforce length limits to protect rendering engine performance
    if len(latex_str) > 500:
        return False
    
    return True


def sanitize_latex(latex_str: str) -> str:
    """
    Cleans up human typos or messy bracket groupings from generated LaTeX strings.
    """
    if not latex_str:
        return latex_str
    
    # If it doesn't look like standard LaTeX code, bypass sanitization
    if '\\' not in latex_str and '{' not in latex_str and '}' not in latex_str:
        return latex_str
    
    # Collapse multiple spaces down to a single space
    latex_str = re.sub(r'\s+', ' ', latex_str.strip())
    
    # Collapse repeated opening or closing curly braces
    latex_str = re.sub(r'\{\{+', '{', latex_str)
    latex_str = re.sub(r'\}+\}', '}', latex_str)
    latex_str = re.sub(r'\}\{', '}{', latex_str)
    
    # Fix duplicated left or right alignment markers
    latex_str = re.sub(r'\\left\\left', '\\left', latex_str)
    latex_str = re.sub(r'\\right\\right', '\\right', latex_str)
    
    # Dynamically balance unmatched curly braces at the end
    open_braces = latex_str.count('{')
    close_braces = latex_str.count('}')
    if open_braces > close_braces:
        latex_str += '}' * (open_braces - close_braces)
    
    while latex_str.endswith('}') and latex_str.count('}') > latex_str.count('{'):
        latex_str = latex_str[:-1]
    
    # Dynamically balance unmatched parentheses at the end
    open_parens = latex_str.count('(')
    close_parens = latex_str.count(')')
    if open_parens > close_parens:
        latex_str += ')' * (open_parens - close_parens)
    elif close_parens > open_parens:
        while latex_str.endswith(')') and latex_str.count(')') > latex_str.count('('):
            latex_str = latex_str[:-1]
            
    return latex_str


def expr_to_clean_text(expr) -> str:
    """
    Converts a SymPy expression into plain math text, replacing python syntax exponents.
    Example: 2**3 -> 2^3
    """
    try:
        return sp.sstr(sp.simplify(expr)).replace("**", "^").replace(" ", "")
    except Exception:
        return sp.sstr(expr).replace("**", "^").replace(" ", "")


def safe_latex(expr) -> str:
    """
    Converts a SymPy expression to a safe LaTeX string. Falls back to clean text if invalid.
    """
    try:
        raw_latex = sp.latex(expr)
        clean_latex = sanitize_latex(raw_latex)
        
        if not is_valid_latex(clean_latex):
            return expr_to_clean_text(expr)
            
        return clean_latex
    except Exception:
        try:
            return expr_to_clean_text(expr)
        except Exception:
            return str(expr)


def format_long_expression(expr, max_length: int = 60) -> str:
    """
    Breaks massive LaTeX math chains onto multiple lines at top-level operator marks.
    """
    try:
        latex_str = safe_latex(expr)
        if len(latex_str) <= max_length:
            return latex_str
        
        if '+' in latex_str or '-' in latex_str:
            parts = []
            current_part = ""
            brace_level = 0
            
            for i, char in enumerate(latex_str):
                if char == '{':
                    brace_level += 1
                elif char == '}':
                    brace_level -= 1
                
                current_part += char
                
                if brace_level == 0 and char in ['+', '-'] and i > 0:
                    if len(current_part.strip()) > 0:
                        parts.append(current_part.strip())
                        current_part = ""
                elif len(current_part) > max_length and brace_level == 0:
                    parts.append(current_part.strip())
                    current_part = ""
            
            if current_part.strip():
                parts.append(current_part.strip())
            
            if len(parts) > 1:
                formatted_parts = []
                for i, part in enumerate(parts):
                    part = part.strip()
                    if i > 0 and not part.startswith(('+', '-')):
                        part = '+' + part
                    formatted_parts.append(part)
                return ' \\\\\n\\quad '.join(formatted_parts)
                
        return latex_str
    except Exception:
        return safe_latex(expr)


def matrix_to_latex(matrix) -> str:
    """
    Converts a SymPy matrix structure into standard LaTeX matrix syntax blocks.
    Bypasses generic text fallback to ensure proper frontend matrix rendering.
    """
    try:
        # SymPy natively generates clean \left[\begin{matrix} layout for matrices
        return sp.latex(matrix)
    except Exception:
        return str(matrix)


def format_matrix_text_grid(matrix) -> str:
    """
    Builds a clean, aligned Unicode text block visual representation of a matrix.
    Used for clean CLI or fallback outputs.
    """
    if not hasattr(matrix, 'rows') or not hasattr(matrix, 'cols'):
        return str(matrix)
        
    rows, cols = matrix.rows, matrix.cols
    matrix_data = []
    
    for i in range(rows):
        row = []
        for j in range(cols):
            row.append(expr_to_clean_text(matrix[i, j]))
        matrix_data.append(row)
        
    col_widths = [max(len(matrix_data[i][j]) for i in range(rows)) for j in range(cols)]
    
    lines = ["┌" + " " * (sum(col_widths) + 3 * (cols - 1) + 2) + "┐"]
    for i in range(rows):
        row_strs = [matrix_data[i][j].rjust(col_widths[j]) for j in range(cols)]
        lines.append("│ " + "   ".join(row_strs) + " │")
    lines.append("└" + " " * (sum(col_widths) + 3 * (cols - 1) + 2) + "┘")
    
    return "\n".join(lines)