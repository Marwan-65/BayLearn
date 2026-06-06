### Project Structure
```
Equation_Solving_Module/
├── src/
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
|       |   └── helpers.py      # Helper functions
│       └── ui/                 # react UI
├── tests/                      # Test suite
├── examples/                   # Example usage
├── pyproject.toml             # Project configuration
├── requirements.txt           # Dependencies (legacy)
└── README.md
```
### Setup
1. Create and activate a virtual environment

```bash
python -m venv venv
.\venv\Scripts\Activate.ps1
```
2. Install the package in development mode:

```bash
pip install -e .
```

3. Add the Groq API key to a `.env` file in the project root:
```env
GROQ_API_KEY=your_key_here
```
### Running the Application
```bash
uvicorn src.api:app --reload --port 9001
```
Access at `http://localhost:9001`
- API documentation: `http://localhost:9001/docs`
