# Adaptive Learning Module

Backend service for BayLearn adaptive sessions. It orchestrates session lifecycle, tracks learner progress, and calls the question-generation module.

## What this module provides

- Flask API for adaptive sessions (`/session/start`, `/session/status`, `/session/answer`, `/session/report`)
- Student level endpoint (`/student/level`)
- Swagger UI docs (`/docs`)
- EPPO inference integration via `app/eppo_inference.py`

## Prerequisites

- Python 3.12 recommended
- PostgreSQL databases reachable for:
  - concept DB
  - chunk DB
- Question Generation module running on port `8001` (or another configured URL)

## Install dependencies

From the module root (`Adaptive-Learning-Module`):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Configure environment

Create .env file:

- `Adaptive-Learning-Module/app/.env`

With at least:

```env
CONCEPT_DB_URL=postgresql+psycopg2://USER:PASSWORD@HOST:5432/CONCEPT_DB
CHUNK_DB_URL=postgresql+psycopg2://USER:PASSWORD@HOST:5432/CHUNK_DB
QUESTION_GEN_BASE_URL=http://localhost:8001
GROQ_API_KEY=your_groq_key_here
```
Check .env.example

Notes:

- `QUESTION_GEN_BASE_URL` defaults to `http://localhost:8001` if omitted.
- `backend.py` and `eppo_inference.py` load `.env` from the `app` folder.

## Run the backend server

Option A (from module root):

```powershell
cd app
python backend.py
```

Option B (staying in module root):

```powershell
python app/backend.py
```

Expected startup:

- API base: `http://localhost:8002`
- Swagger UI: `http://localhost:8002/docs`

## Quick health checks

```powershell
curl http://localhost:8002/
curl "http://localhost:8002/student/level?user_id=YOUR_USER_UUID"
```

## Frontend integration

Frontend should point to:

```env
VITE_ADAPTIVE_API_BASE=http://localhost:8002
```

The backend includes a restrictive CORS policy for local frontend origins:

- `http://localhost:5173`
- `http://127.0.0.1:5173`
- `http://localhost:3000`
- `http://127.0.0.1:3000`

## Common issues

### 1) Server exits immediately with env errors

If you see errors like `CONCEPT_DB_URL not set` or `CHUNK_DB_URL not set`, verify:

- `app/.env` exists
- variable names are exact
- values are valid DB URLs

### 2) Import/module errors

Reinstall dependencies in the active environment:

```powershell
pip install -r requirements.txt
```

### 3) Adaptive question generation returns 400

Check that:

- question-generation service is running (`http://localhost:8001`)
- RAG/indexed project IDs exist and are queryable
- adaptive session config uses `file_ids` as a comma-separated string in the question-generation API contract

## Project structure (relevant files)

- `app/backend.py` — Flask API + orchestration
- `app/eppo_inference.py` — adaptive policy/inference loop
- `app/db_models.py` — DB table helpers
- `requirements.txt` — Python dependencies