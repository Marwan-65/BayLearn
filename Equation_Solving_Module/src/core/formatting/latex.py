import re
import sympy as sp

# Trig/log function names SymPy uses in LaTeX output
_TRIG = r'(?:arc(?:sin|cos|tan)|sinh|cosh|tanh|sin|cos|tan|cot|sec|csc|log|ln|exp)'

def sanitize_latex_artifacts(text: str) -> str:
    if not text:
        return ""
    s = str(text)

    # Unicode minus → ASCII minus
    s = s.replace('\u2212', '-').replace('−', '-')

    # \tmspace / \nobreakspace / \mathspace → thin space \,
    s = re.sub(r'\\tmspace\s*\+\s*[\d.]+[a-z]+', r'\\,', s)
    s = re.sub(r'\\tmspace\b[^}]*}?', r'\\,', s)
    s = re.sub(r'\\nobreakspace\b', r'~', s)
    s = re.sub(r'\\mathspace\b', r'\\,', s)

    # SymPy emits \sin{\left(x\right)} — KaTeX rejects \sin{...} containing \left.
    # Fix: \sin{\left( → \sin\left(  and  \right)} → \right)
    s = re.sub(r'(\\' + _TRIG + r')\{(\\left\b)', r'\1\2', s)
    s = re.sub(r'(\\right\s*[)\]])\}', r'\1', s)

    return s.strip()


def safe_latex(expr) -> str:
    if isinstance(expr, tuple) and len(expr) == 1:
        expr = expr[0]
    try:
        raw_latex = sp.latex(expr)
        return sanitize_latex_artifacts(raw_latex)
    except Exception:
        try:
            return expr_to_clean_text(expr)
        except Exception:
            return str(expr).replace("**", "^").strip()


def expr_to_clean_text(expr) -> str:
    try:
        return sp.sstr(sp.simplify(expr)).replace("**", "^").strip()
    except Exception:
        return sp.sstr(expr).replace("**", "^").strip()


def matrix_to_latex(matrix) -> str:
    try:
        return sanitize_latex_artifacts(sp.latex(matrix))
    except Exception:
        return str(matrix)