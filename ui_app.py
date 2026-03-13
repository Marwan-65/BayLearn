import re
from datetime import datetime
import sympy as sp
import streamlit as st
from sympy.parsing.sympy_parser import (
    parse_expr,
    standard_transformations,
    implicit_multiplication_application,
)
from level2_solver import level_2_solver

st.set_page_config(
    page_title="BayLearn Math Solver",
    page_icon="",
    layout="wide",
)

st.markdown(
    """
    <style>
    @keyframes fadeInUp {
        from {
            opacity: 0;
            transform: translateY(10px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    @keyframes softGlow {
        0% { box-shadow: 0 8px 20px rgba(57, 38, 112, 0.08); }
        50% { box-shadow: 0 10px 26px rgba(123, 60, 255, 0.16); }
        100% { box-shadow: 0 8px 20px rgba(57, 38, 112, 0.08); }
    }
    .main {
        background: radial-gradient(circle at 10% 0%, #fff6d6 0%, #ffeef9 38%, #eef7ff 100%);
    }
    .hero {
        padding: 1.25rem 1.5rem;
        border-radius: 16px;
        border: 1px solid rgba(123, 60, 255, 0.35);
        background: linear-gradient(120deg, rgba(123, 60, 255, 0.14), rgba(0, 166, 251, 0.12), rgba(255, 0, 110, 0.08));
        margin-bottom: 1rem;
        box-shadow: 0 8px 24px rgba(68, 41, 163, 0.12);
        animation: fadeInUp 420ms ease-out;
        transition: transform 160ms ease, box-shadow 160ms ease;
    }
    .hero:hover {
        transform: translateY(-2px);
        box-shadow: 0 12px 30px rgba(68, 41, 163, 0.2);
    }
    .hero h1 {
        margin: 0;
        color: #1f1147;
        font-size: 1.9rem;
        font-weight: 700;
    }
    .hero p {
        margin: 0.45rem 0 0;
        color: #32206f;
        font-size: 1rem;
    }
    .panel {
        border-radius: 14px;
        border: 1px solid rgba(123, 60, 255, 0.22);
        background: rgba(255, 255, 255, 0.84);
        padding: 1rem;
        box-shadow: 0 8px 20px rgba(57, 38, 112, 0.08);
        animation: fadeInUp 450ms ease-out;
        transition: transform 160ms ease, box-shadow 160ms ease, border-color 160ms ease;
    }
    .panel:hover {
        transform: translateY(-2px);
        border-color: rgba(123, 60, 255, 0.35);
        box-shadow: 0 12px 26px rgba(57, 38, 112, 0.14);
    }
    .chips {
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem;
        margin: 0.4rem 0 0.2rem;
    }
    .chip {
        padding: 0.26rem 0.62rem;
        border-radius: 999px;
        border: 1px solid rgba(105, 68, 197, 0.35);
        background: rgba(124, 58, 237, 0.10);
        color: #2a195b;
        font-size: 0.82rem;
        font-weight: 600;
    }
    .small-note {
        color: #4a377f;
        font-size: 0.92rem;
        margin-top: 0.35rem;
    }
    .panel-divider {
        margin: 1rem 0 1.2rem;
        height: 10px;
        border-radius: 999px;
        background: linear-gradient(90deg, #7b3cff 0%, #00a6fb 45%, #ff006e 100%);
        opacity: 0.75;
        animation: softGlow 3.4s ease-in-out infinite;
    }
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, rgba(123, 60, 255, 0.09) 0%, rgba(0, 166, 251, 0.08) 55%, rgba(255, 0, 110, 0.07) 100%);
        border-right: 1px solid rgba(123, 60, 255, 0.22);
    }
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] .stMarkdown,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] label {
        color: #24124f !important;
    }
    section[data-testid="stSidebar"] .stButton button {
        background: linear-gradient(90deg, #5b21b6 0%, #7c3aed 45%, #4f46e5 100%) !important;
        color: #ffffff !important;
        border: 1px solid #2f1f66 !important;
    }
    section[data-testid="stSidebar"] .stButton button:hover {
        filter: brightness(1.05);
        transform: translateY(-1px);
    }
    .stButton button {
        transition: transform 140ms ease, filter 140ms ease, box-shadow 140ms ease;
    }
    .stButton button:hover {
        transform: translateY(-1px);
        filter: brightness(1.03);
    }
    .stButton button:active {
        transform: translateY(0);
    }
    @media (prefers-color-scheme: dark) {
        .chip {
            border-color: rgba(220, 194, 255, 0.45);
            background: rgba(196, 181, 253, 0.18);
            color: #f6edff;
        }
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, rgba(76, 29, 149, 0.28) 0%, rgba(30, 64, 175, 0.24) 55%, rgba(157, 23, 77, 0.2) 100%);
            border-right: 1px solid rgba(220, 194, 255, 0.35);
        }
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] .stMarkdown,
        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] span,
        section[data-testid="stSidebar"] label {
            color: #f6edff !important;
        }
        section[data-testid="stSidebar"] .stButton button {
            background: #1e40af !important;
            color: #ffffff !important;
            border: 1px solid #bfdbfe !important;
        }
    }
    @media (prefers-reduced-motion: reduce) {
        .hero,
        .panel,
        .panel-divider,
        .stButton button {
            animation: none !important;
            transition: none !important;
            transform: none !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
      <h1>BayLearn Math Solver</h1>
            <p>Write math in plain language and get readable equations, clear steps, and final answers in LaTeX.</p>
            <div class="chips">
                <span class="chip">Natural Language Input</span>
                <span class="chip">LaTeX Equation Output</span>
                <span class="chip">Step-by-Step Reasoning</span>
            </div>
    </div>
    """,
    unsafe_allow_html=True,
)

def apply_wcag_aaa_theme():
    st.markdown(
        """
        <style>
        :root {
                    --bg: #fff8ff;
                    --surface: #ffffff;
                    --text: #1a103d;
                    --muted: #34215f;
                    --primary: #4c1d95;
                    --border: #3f2c77;
        }

        @media (prefers-color-scheme: dark) {
          :root {
                        --bg: #0f0b1f;
                        --surface: #1b1435;
                        --text: #f8f4ff;
                        --muted: #f0e7ff;
                                                --primary: #1d4ed8;
                                                --border: #bfdbfe;
          }
        }

        .stApp { background: var(--bg); color: var(--text); }
        .stMarkdown, p, span, label, div { color: var(--text) !important; }
        .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] > div {
          background: var(--surface) !important;
          color: var(--text) !important;
          border: 1px solid var(--border) !important;
        }
        .stButton button {
          background: var(--primary) !important;
          color: #FFFFFF !important;
          border: 1px solid var(--border) !important;
          font-weight: 600;
        }
        .stCodeBlock, code {
          background: var(--surface) !important;
          color: var(--text) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

apply_wcag_aaa_theme()

if "history" not in st.session_state:
    st.session_state.history = []
if "last_result" not in st.session_state:
    st.session_state.last_result = "Your solution will appear here."
if "user_input" not in st.session_state:
    st.session_state.user_input = "Solve 2x + y = 10 and x - y = 2"
if "trace_equation" not in st.session_state:
    st.session_state.trace_equation = "y = x^2"
if "trace_x_values" not in st.session_state:
    st.session_state.trace_x_values = "-2, -1, 0, 1, 2"

def _to_sympy_expr(text):
    normalized = text.strip().replace("^", "**")
    return sp.sympify(normalized, evaluate=False)

def _parse_math_expr(text):
    transformations = standard_transformations + (implicit_multiplication_application,)
    return parse_expr(text.strip().replace("^", "**"), transformations=transformations)

def _parse_equation_input(text):
    x_symbol, y_symbol = sp.symbols("x y")
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("Enter an equation first.")

    if "=" in cleaned:
        left_text, right_text = cleaned.split("=", 1)
        left_expr = _parse_math_expr(left_text)
        right_expr = _parse_math_expr(right_text)
        equation = sp.Eq(left_expr, right_expr)
    else:
        equation = sp.Eq(y_symbol, _parse_math_expr(cleaned))

    branches = sp.solve(equation, y_symbol)
    if not branches:
        raise ValueError("Could not isolate y as a function of x.")

    return x_symbol, y_symbol, equation, branches

def _parse_x_values(text):
    values = []
    for item in text.split(","):
        token = item.strip()
        if not token:
            continue
        try:
            values.append(float(token))
        except ValueError as exc:
            raise ValueError(f"Invalid x value: {token}") from exc
    if not values:
        raise ValueError("Provide at least one x value.")
    return values

def _format_numeric(expr_value):
    simplified = sp.N(expr_value)
    if getattr(simplified, "is_real", None) is False or simplified.has(sp.I):
        return "undefined"
    try:
        return float(simplified)
    except Exception:
        return "undefined"

def _build_trace_rows(x_symbol, branches, x_values):
    rows = []
    for x_value in x_values:
        row = {"x": x_value}
        for index, branch in enumerate(branches, start=1):
            raw_value = branch.subs(x_symbol, x_value)
            cell = _format_numeric(raw_value)
            key = "y" if len(branches) == 1 else f"y{index}"
            row[key] = cell
        rows.append(row)
    return rows

def render_tracing_table():
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.subheader("Tracing Table")
    st.caption("Deterministic mode: pure SymPy (no AI call).")

    trace_input_col, range_col = st.columns([1.4, 1])
    with trace_input_col:
        trace_equation = st.text_input(
            "Equation in x and y",
            value=st.session_state.trace_equation,
            placeholder="Example: y = 2x^2 + 1 or x^2 + y = 10",
        )
    with range_col:
        range_start = st.number_input("x start", value=-2.0, step=1.0)
        range_end = st.number_input("x end", value=2.0, step=1.0)
        range_step = st.number_input("x step", min_value=0.1, value=1.0, step=0.1)

    generate_default = st.button("Generate x range", use_container_width=True)
    if generate_default:
        generated = []
        cursor = range_start
        max_iterations = 1000
        iterations = 0
        while cursor <= range_end + 1e-9 and iterations < max_iterations:
            generated.append(f"{cursor:g}")
            cursor += range_step
            iterations += 1
        st.session_state.trace_x_values = ", ".join(generated)

    x_values_text = st.text_input(
        "x values (comma-separated)",
        value=st.session_state.trace_x_values,
        placeholder="Example: -2, -1, 0, 1, 2",
    )

    trace_clicked = st.button("Build tracing table", type="primary", use_container_width=True)

    if trace_clicked:
        st.session_state.trace_equation = trace_equation.strip()
        st.session_state.trace_x_values = x_values_text.strip()

    if st.session_state.trace_equation and st.session_state.trace_x_values:
        try:
            x_symbol, _, equation, branches = _parse_equation_input(st.session_state.trace_equation)
            x_values = _parse_x_values(st.session_state.trace_x_values)

            st.markdown("#### Parsed Equation")
            st.latex(f"{sp.latex(equation.lhs)} = {sp.latex(equation.rhs)}")

            st.markdown("#### y(x) Branches")
            for index, branch in enumerate(branches, start=1):
                label = "y" if len(branches) == 1 else f"y_{index}"
                st.latex(f"{label} = {sp.latex(branch)}")

            rows = _build_trace_rows(x_symbol, branches, x_values)
            st.markdown("#### Table")
            st.dataframe(rows, use_container_width=True)
        except Exception as trace_error:
            st.warning(str(trace_error))

    st.markdown('</div>', unsafe_allow_html=True)

def _render_math_equation(left_text, right_text):
    try:
        left_expr = _to_sympy_expr(left_text)
        right_expr = _to_sympy_expr(right_text)
        st.latex(f"{sp.latex(left_expr)} = {sp.latex(right_expr)}")
    except Exception:
        st.write(f"{left_text} = {right_text}")

def _render_solution_assignments(text):
    chunks = [chunk.strip() for chunk in text.split("|") if chunk.strip()]
    for chunk in chunks:
        if ":" in chunk:
            label, body = chunk.split(":", 1)
            st.markdown(f"**{label.strip()}**")
        else:
            body = chunk

        assignments = [part.strip() for part in body.split(",") if "=" in part]
        if not assignments:
            st.write(chunk)
            continue

        for assignment in assignments:
            left_text, right_text = assignment.split("=", 1)
            _render_math_equation(left_text, right_text)

def render_solver_output(output_text):
    final_match = re.search(r"Final Result:\s*(.+)$", output_text, flags=re.S)
    steps_text = output_text.strip()
    final_text = ""

    if final_match:
        steps_text = output_text[:final_match.start()].strip()
        final_text = final_match.group(1).strip()

    if steps_text:
        with st.expander("Show solution steps", expanded=True):
            for raw_line in steps_text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue

                if line.startswith("Step "):
                    st.markdown(f"**{line}**")
                    continue

                if ":" in line and "=" in line:
                    prefix, expression_part = line.split(":", 1)
                    left_text, right_text = expression_part.split("=", 1)
                    st.write(prefix.strip())
                    _render_math_equation(left_text, right_text)
                    continue

                if line.startswith("Eq") and "=" in line:
                    left_text, right_text = line.split("=", 1)
                    _render_math_equation(left_text, right_text)
                    continue

                if " = " in line:
                    left_text, right_text = line.split("=", 1)
                    _render_math_equation(left_text, right_text)
                    continue

                st.write(line)

    if final_text:
        st.markdown("#### Final Result")
        if "=" in final_text and not final_text.startswith("[") and not final_text.startswith("("):
            _render_solution_assignments(final_text)
        else:
            try:
                final_expr = _to_sympy_expr(final_text)
                st.latex(sp.latex(final_expr))
            except Exception:
                st.write(final_text)

with st.sidebar:
    st.header("History")
    st.caption(f"Solved: {len(st.session_state.history)} prompt(s)")
    if st.button("Clear history", use_container_width=True):
        st.session_state.history = []

    with st.expander("Recent solves", expanded=True):
        if not st.session_state.history:
            st.caption("No solved prompts yet.")
        else:
            for index, item in enumerate(reversed(st.session_state.history), start=1):
                label = item["prompt"]
                if len(label) > 42:
                    label = f"{label[:39]}..."
                solved_at = item.get("timestamp", "recent")
                st.caption(f"{solved_at}")
                if st.button(f"{index}. {label}", key=f"history_{index}", use_container_width=True):
                    st.session_state.user_input = item["prompt"]
                    st.session_state.last_result = item["result"]

st.markdown('<div class="panel">', unsafe_allow_html=True)
st.subheader("Input")

sample_prompts = {
    "Linear system": "Solve 2x + y = 10 and x - y = 2",
    "Derivative": "what is the derivative of e^-2x sin(3x) with respect to x",
    "Integral": "integrate x^2 * exp(x) with respect to x",
}

selected_example = st.selectbox("Quick examples", list(sample_prompts.keys()))

default_text = sample_prompts[selected_example]
if st.button("Use selected example", use_container_width=True):
    st.session_state.user_input = default_text

user_input = st.text_area(
    "Enter your math request",
    value=st.session_state.user_input,
    height=160,
    placeholder="Example: Solve 3x + 2 = 11",
)

show_translation = st.toggle("Show AI translation JSON", value=False)
solve_clicked = st.button("Solve", type="primary", use_container_width=True)

st.markdown(
    '<p class="small-note">Tip: You can write equations normally (e.g., 2x + y = 10).</p>',
    unsafe_allow_html=True,
)
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="panel-divider"></div>', unsafe_allow_html=True)

st.markdown('<div class="panel">', unsafe_allow_html=True)
st.subheader("Output")

if solve_clicked:
    cleaned_input = user_input.strip()
    st.session_state.user_input = cleaned_input
    if not cleaned_input:
        st.warning("Please enter a math prompt first.")
    else:
        with st.spinner("Solving with SymPy + AI translation..."):
            try:
                response_text = level_2_solver(cleaned_input, show_translation=show_translation)
                st.session_state.last_result = response_text
                st.session_state.history.append(
                    {
                        "prompt": cleaned_input,
                        "result": response_text,
                        "timestamp": datetime.now().strftime("%H:%M")
                    }
                )
                if len(st.session_state.history) > 20:
                    st.session_state.history = st.session_state.history[-20:]
            except Exception as exc:
                st.session_state.last_result = f"System Error: {exc}"

render_solver_output(st.session_state.last_result)
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="panel-divider"></div>', unsafe_allow_html=True)
render_tracing_table()

st.caption("Powered by Groq + SymPy")
