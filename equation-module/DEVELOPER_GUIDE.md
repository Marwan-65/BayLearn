"""Developer Guide for BayLearn

This guide explains the structure and conventions of the BayLearn module.

## Project Structure (Cookiecutter Compliant)

```
baylearn/
├── src/
│   └── baylearn/                    # Main package (installed package)
│       ├── __init__.py              # Package entry point
│       ├── core/                    # Core solver components
│       │   ├── __init__.py
│       │   ├── config.py            # Configuration and constants
│       │   ├── llm_client.py        # LLM API wrapper
│       │   ├── parser.py            # Simple equation parser
│       │   └── solver.py            # Main solver with all helpers
│       ├── api/                     # FastAPI application
│       │   ├── __init__.py
│       │   ├── models.py            # Pydantic data models
│       │   ├── routes.py            # API endpoints
│       │   └── static/              # UI resources
│       └── ui/                      # Streamlit UI
│           ├── __init__.py
│           ├── app.py               # Main UI application
│           └── static/              # Static assets (CSS, JS, etc.)
├── tests/                           # Test suite
│   ├── test_solver.py
│   ├── test_api.py
│   └── test_parser.py
├── examples/                        # Usage examples
│   └── basic_usage.py
├── docs/                            # Documentation
├── pyproject.toml                   # Project configuration (PEP 517/518)
├── requirements.txt                 # Dependency list (legacy format)
├── MANIFEST.in                      # Distribution manifest
├── README.md                        # Project README
├── run.py                           # Entry point script
└── .env.example                     # Example environment variables
```

## Installation for Development

```bash
# Clone repository
git clone https://github.com/Marwan-65/BayLearn.git
cd BayLearn

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install in development mode
pip install -e .

# Install with development dependencies
pip install -e ".[dev]"

# Setup environment
cp .env.example .env
# Edit .env and add your GROQ_API_KEY
```

## Module Architecture

### Core Module (`src/baylearn/core/`)

**config.py**

- Centralized configuration and constants
- System prompts, model names, LaTeX validation settings
- Valid matrix operations, expression lengths, etc.
- Any magic numbers or settings should go here

**llm_client.py**

- Handles LLM API communication
- Isolated from solver logic for reusability
- Use `translate_math_input()` to get structured math data

**parser.py**

- Simple SymPy-based equation parser
- Standalone functionality for basic math string parsing
- Use when you don't need AI translation

**solver.py**

- Main solver engine with all helper functions
- Private helper functions (\_is_valid_latex, \_format_dsolve_steps, etc.)
- Public main function: `level_2_solver()`
- Also exports: `_extract_graphable_functions()` for API use

**Import pattern in core:**

```python
from .config import SYSTEM_PROMPT, MODEL_NAME
from .llm_client import translate_math_input

# For type hints
from typing import Dict, Any, List, Tuple
```

### API Module (`src/baylearn/api/`)

**models.py**

- Pydantic models for request/response validation
- SolveRequest, SolveResponse, GraphableFunction
- No business logic, only data definitions

**routes.py**

- FastAPI app and endpoint definitions
- Uses models from .models
- Imports solver from ..core.solver
- Helper functions for parsing output

****init**.py**

- Exports the FastAPI app for external use
- Allows: `from baylearn.api import app`

**Import pattern in API:**

```python
from ..core.solver import level_2_solver
from .models import SolveRequest, SolveResponse
```

### UI Module (`src/baylearn/ui/`)

**app.py**

- Streamlit web interface
- Imports solver from ..core.solver
- No API logic, only presentation

****init**.py**

- Exports the main function if needed

**static/**

- CSS, JavaScript, images
- Frontend assets

**Import pattern in UI:**

```python
from ..core.solver import level_2_solver
```

### Top-level Package (`src/baylearn/`)

****init**.py**

- Public API
- Re-exports main functions
- Users do: `from baylearn import level_2_solver`

```python
from .core.solver import level_2_solver
from .core.parser import solve_math_string

__all__ = ["level_2_solver", "solve_math_string"]
```

## Adding New Features

### Add a new operation to the solver:

1. In `config.py`: Add any needed constants
2. In `solver.py`: Add handler in `_solve_from_ai_data()`
3. In `solver.py`: Add formatting function (e.g., `_format_*_steps()`)
4. Test with `examples/basic_usage.py`
5. Add API test in `tests/test_api.py`

### Add a new API endpoint:

1. In `api/models.py`: Define request/response models
2. In `api/routes.py`: Add route handler
3. Update `api/__init__.py` if exporting new objects
4. Document in README.md
5. Add test in `tests/test_api.py`

### Add a new UI feature:

1. Update `ui/app.py` with new UI components
2. Use existing solver functions from `..core.solver`
3. Test locally: `python run.py ui`

## Running Different Parts

```bash
# Run Streamlit UI
python run.py ui

# Run FastAPI server
python run.py api

# Run examples
python run.py example

# Direct Python
python -c "from baylearn import level_2_solver; print(level_2_solver('Solve x = 5'))"
```

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=src/baylearn --cov-report=html

# Run specific test file
pytest tests/test_solver.py -v

# Run specific test
pytest tests/test_solver.py::test_basic_equation -v
```

## Code Style

```bash
# Format code
black src/ tests/ examples/

# Check lint
flake8 src/baylearn

# Type checking
mypy src/baylearn
```

## Dependencies

**Always** use `pyproject.toml` for dependency management:

- Add new dependencies to `[project.dependencies]`
- Add dev dependencies to `[project.optional-dependencies]` → dev
- Update `requirements.txt` mirrors the pyproject.toml for legacy compatibility

```toml
[project]
dependencies = [
    "new-package>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "new-dev-tool>=2.0.0",
]
```

## Import Conventions

**Package internal imports (use relative):**

```python
# In src/baylearn/api/routes.py
from ..core.solver import level_2_solver    # ✓ Good
from baylearn.core.solver import level_2_solver  # ✗ Don't use inside package
```

**External imports (use absolute):**

```python
# In examples/basic_usage.py
from baylearn import level_2_solver  # ✓ Good
```

## Debugging

Enable debug output:

```python
from baylearn.core.solver import level_2_solver

# With AI translation visible
result, translation = level_2_solver(
    "your query",
    show_translation=True,
    return_translation=True
)
print(f"Operation: {translation['operation']}")
```

## Common Issues

**Import errors after installation:**

```bash
pip install -e .  # Reinstall in dev mode
```

**GROQ_API_KEY not found:**

- Create `.env` file with your key
- Check `.env` is in project root (where run.py is)

**Streamlit complains about script rerun:**

- This is normal behavior, not an error

**API endpoints returning 500 errors:**

- Check API server logs for detailed error messages
- Verify GROQ_API_KEY is set

## Resources

- [Cookiecutter Project Structure](https://cookiecutter-pypackage.readthedocs.io/en/latest/structure.html)
- [Python Packaging Guide](https://packaging.python.org/)
- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [Streamlit Docs](https://docs.streamlit.io/)
- [SymPy Docs](https://docs.sympy.org/)
  """
