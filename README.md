## BayLearn

BayLearn is a neuro-symbolic math solver that translates natural language math prompts into SymPy operations and returns step-by-step results.

### Features

- Solve equations and equation systems
- Compute derivatives
- Compute integrals
- Show student-friendly linear solving steps when possible
- Use a modern Streamlit UI

### Setup

1. Create and activate a virtual environment (recommended).
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Add your Groq API key to a `.env` file in the project root:

```env
GROQ_API_KEY=your_key_here
```

### Run UI

```bash
streamlit run ui_app.py
```

### Run solver script directly

```bash
python level2_solver.py
```
