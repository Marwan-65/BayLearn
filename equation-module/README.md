## BayLearn

BayLearn is a neuro-symbolic math solver that translates natural language math prompts into SymPy operations and returns step-by-step results. It follows the cookiecutter project structure for maintainability and scalability.

### Project Structure

```
baylearn/
├── src/
│   └── baylearn/              # Main package
│       ├── __init__.py
│       ├── core/              # Core solver components
│       │   ├── __init__.py
│       │   ├── config.py       # Configuration and constants
│       │   ├── llm_client.py   # LLM API wrapper
│       │   ├── parser.py       # Math expression parser
│       │   └── solver.py       # Main solver logic
│       ├── api/                # FastAPI application
│       │   ├── __init__.py
│       │   ├── models.py       # Pydantic models
│       │   └── routes.py       # API endpoints
│       └── ui/                 # Streamlit UI
│           ├── __init__.py
│           ├── app.py          # Main UI application
│           └── static/         # Static assets
├── tests/                      # Test suite
├── examples/                   # Example usage
├── pyproject.toml             # Project configuration
├── requirements.txt           # Dependencies (legacy)
└── README.md
```

### Features

- Solve equations and equation systems
- Compute derivatives
- Compute integrals
- Show student-friendly linear solving steps when possible
- Use a modern Streamlit UI
- FastAPI endpoint for RAG pipeline integration
- Organized cookiecutter-compliant structure

### Setup

1. Create and activate a virtual environment (recommended):

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install the package in development mode:

```bash
pip install -e .
```

Or, for development with all optional dependencies:

```bash
pip install -e ".[dev]"
```

3. Add your Groq API key to a `.env` file in the project root:

```env
GROQ_API_KEY=your_key_here
```

### Running the Application

#### Run React UI

```bash
python run.py ui
```

This starts the React TypeScript UI on `http://localhost:5173` and the local API on `http://127.0.0.1:8000`.

#### Run FastAPI Server

```bash
uvicorn baylearn.api:app --reload
```

Access at `http://localhost:8000`

- API documentation: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

#### Run Solver Directly

```bash
python -c "from baylearn import level_2_solver; print(level_2_solver('Solve 2x + 5 = 15'))"
```

#### Run the frontend directly

```bash
cd src/baylearn-frontend
npm run dev
```

### Usage as a Module

```python
from baylearn import level_2_solver, solve_math_string

# Using the advanced solver
result = level_2_solver("Solve x^2 - 4 = 0")
print(result)

# Using the simple parser
simple_result = solve_math_string("2y - 4 = 14")
print(simple_result)
```

### Development

Run tests:

```bash
pytest tests/ -v --cov=src/baylearn
```

Format code:

```bash
black src/ tests/
```

Type checking:

```bash
mypy src/baylearn
```

### Dependencies

**Core:**

- `sympy>=1.12` - Symbolic mathematics
- `groq>=0.4.0` - LLM API client
- `python-dotenv>=1.0.0` - Environment variables

**API:**

- `fastapi>=0.104.0` - Web framework
- `uvicorn>=0.24.0` - ASGI server
- `pydantic>=2.0.0` - Data validation

**UI:**

- `streamlit>=1.28.0` - Interactive web app
- `plotly>=5.17.0` - Graphing library

**Development:**

- `pytest>=7.0.0` - Testing framework
- `black>=23.0.0` - Code formatter
- `flake8>=6.0.0` - Linter
- `mypy>=1.0.0` - Type checker

### Installation from Source

```bash
git clone https://github.com/Marwan-65/BayLearn.git
cd BayLearn
pip install -e .
```

### License

MIT License - see LICENSE file for details

### Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
