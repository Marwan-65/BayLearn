import sympy as sp

def format_sympy_as_plain_text(expr: sp.Expr, simplify: bool = True, strip_spaces: bool = False) -> str:
    if simplify:
        try:
            text = sp.sstr(sp.simplify(expr))
        except (TypeError, ValueError):
            text = sp.sstr(expr)
    else:
        text = sp.sstr(expr)
        
    text = text.replace("**", "^")
    if strip_spaces:
        text = text.replace(" ", "")
    return text
