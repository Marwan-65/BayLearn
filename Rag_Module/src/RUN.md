# Running the full BayLearn pipeline

Exact commands for **this worktree** — copy/paste them as-is.

Repo root (what every path below starts from):

```
/Users/manarfarghaly/Desktop/Data/senior2firstterm/GP MVP/GP/BayLearn/.claude/worktrees/interesting-goldberg
```

Layout you have:

```
interesting-goldberg/
├── src/                         ← orchestrator (RAG backend + frontend)
│   └── baylearn-frontend/       ← React UI
├── Input-Parsing-Module/        ← teammate's FastAPI (app.main:app)
├── equation-module/             ← teammate's FastAPI + Streamlit UI
└── Visualizer/
    └── Linked List Animation/   ← teammate's static HTML visualizer
```

Everything below assumes you already `cd` into `interesting-goldberg/`.

---

## You need **5 terminal tabs** running at the same time

| Tab | Runs                                    | Port |
| --: | --------------------------------------- | ---: |
|   1 | Input-parsing module (FastAPI)          | 8100 |
|   2 | Equation module — FastAPI backend       | 9001 |
|   3 | Equation module — Streamlit UI          | 8501 |
|   4 | Animation visualizer (static HTML)      | 3001 |
|   5 | Orchestrator backend (the RAG we built) | 8000 |
|   6 | BayLearn frontend (Vite)                | 5173 |

Qdrant is in the cloud — no local container needed. Put your Qdrant Cloud URL + API key in `src/.env` (step 5).

> **Minimum viable demo**: if you only have time for a basic run, you need **tabs 1, 5, 6**. That gets upload + RAG chat working. Tabs 2–4 are only needed if you want the equation/animation buttons and the intent-aware routing.

---

## One-time setup (do this once per module)

> **Why three separate conda envs?** The three Python modules have **incompatible deps** — Input-Parsing-Module needs `numpy>=2` (paddleocr), the orchestrator needs `numpy<2` (langchain). Putting them in one env breaks things, which is exactly what you saw earlier (`httpx` / `pydantic` / `numpy` got force-replaced). One env per module = zero conflicts.

You already have `mini-rag-app` for the orchestrator. Create two more for the teammate modules.

### Input-parsing module → env `baylearn-parsing`

```bash
cd Input-Parsing-Module
conda create -n baylearn-parsing python=3.11 -y
conda activate baylearn-parsing
pip install -r requirements.txt
cp .env.example .env   # edit: GEMINI_API_KEY=..., GROQ_API_KEY=...
conda deactivate
cd ..
```

### Equation module → env `baylearn-equation`

```bash
cd equation-module
conda create -n baylearn-equation python=3.11 -y
conda activate baylearn-equation
pip install -e .
# add a .env if the module requires an LLM key — check equation-module/README.md
conda deactivate
cd ..
```

### Orchestrator (our RAG) → existing env `mini-rag-app`

```bash
cd src
conda activate mini-rag-app
pip install -r requirements.txt     # or: poetry install
cp .env.example .env
# edit .env — see the exact list below
conda deactivate
cd ..
```

**`src/.env` — fill these** (everything else can keep the example defaults):

```bash
# LLM
OPENAI_API_KEY=sk-...
# or GEMINI_API_KEY / GOOGLE_API_KEY depending on your config

# Qdrant Cloud
QDRANT_URL=https://<your-cluster>.qdrant.cloud
QDRANT_API_KEY=<your-qdrant-api-key>

# other modules — URLs the orchestrator will proxy to
INPUT_PARSING_MODULE_URL=http://localhost:8100
EQUATION_MODULE_URL=http://localhost:9001

# Limits we wired in
INPUT_DEFAULT_MAX_CHARACTERS=5000
GENERATION_DEFAULT_MAX_TOKENS=1024
UPLOAD_MAX_MB_PDF=50
UPLOAD_MAX_MB_IMAGE=20
UPLOAD_MAX_MB_AUDIO=200
UPLOAD_MAX_MB_VIDEO=1024
UPLOAD_MAX_MB_DEFAULT=25

# Frontend CORS
CORS_ORIGINS=["http://localhost:5173"]
```

### Frontend

```bash
cd src/baylearn-frontend
npm install
cp .env.example .env.local
# default values match the ports above, no editing needed
cd ../..
```

---

## Every time you want to demo — start these 6 tabs in order

### Tab 1 — Input-parsing module (port 8100)

```bash
cd Input-Parsing-Module
conda activate baylearn-parsing
uvicorn app.main:app --port 8100
```

Verify in another shell:

```bash
curl http://localhost:8100/health
```

### Tab 2 — Equation FastAPI backend (port 9001)

```bash
cd equation-module
conda activate baylearn-equation
uvicorn baylearn.api:app --app-dir src --port 9001
```

Verify:

```bash
curl http://localhost:9001/health
# → {"status":"healthy", ...}
```

### Tab 3 — Equation Streamlit UI (port 8501)

```bash
cd equation-module
conda activate baylearn-equation
python run.py ui
```

This is what opens when the user clicks **Equation Lab ↗** in the sidebar.

### Tab 4 — Animation visualizer (port 3001)

The visualizer is static HTML/JS — no build, no install:

```bash
cd "Visualizer/Linked List Animation"
python -m http.server 3001
```

Open `http://localhost:3001/` to confirm it loads. This is what opens when the user clicks **Animation Lab ↗**.

### Tab 5 — Orchestrator backend (port 8000)

```bash
cd src
conda activate mini-rag-app
uvicorn main:app --reload --port 8200
```

Sanity checks:

```bash
curl http://localhost:8200/api/v1/
# → {"App_name":"...", ...}

curl http://localhost:8200/api/v1/modules/health
# → {"modules":{
#      "equation":{"available":true, ...},
#      "animation":{"available":false, "status":"not_configured"},
#      "input_parsing":{"available":true, ...}
#   }}
```

> `"animation":{"available":false}` is **expected** — the visualizer is a static page with no `/health` endpoint. The sidebar button still works; chat intent routing just won't return a rendered animation payload.

### Tab 6 — BayLearn frontend (port 5173)

```bash
cd src/baylearn-frontend
npm run dev
```

Open `http://localhost:5173`.

---

## ✅ Demo flow (for your mentor)

The UI deliberately has **only three things the user can do**. Walk through them in order:

### 1. Drop study materials into **Sources**

Drag a PDF (or image/audio/video/txt) onto the **Add sources** box in the left sidebar.

- Fires `POST /api/v1/parse/upload/<auto-generated-id>?auto_index=true`
- Orchestrator → Input-Parsing-Module (tab 1) → chunks → embeds → Qdrant Cloud
- File appears in the sidebar list with chunk count + ✓. No "re-index" button — indexing happens automatically.
- The project ID is auto-generated per browser (stored in localStorage). The user never sees or types it.

### 2. Ask a question in chat

The `/nlp/ask/…` endpoint runs the intent classifier first, then routes. Try these three — they're the exact canonical examples from `src/controllers/intent_router.py`:

**a. RAG-only question** (grey "Answering from sources" badge):

> "Summarize the key concepts from my materials"

**b. Equation intent** (orange "Equation mode" badge):

> "Solve the equation from page 3"

The chat bubble inlines the extracted equation + the solver output returned by tab 2.

**c. Animation intent** (green "Animation mode" badge):

> "Animate a linked list insertion"

The chat bubble shows the extracted animation spec. (Note: since the visualizer has no `/run` backend, the rendered animation itself only shows in the sidebar button → new tab. The intent classification + spec extraction still run and display.)

### 3. Open modules directly from the sidebar

- **Equation Lab ↗** → opens the Streamlit UI in tab 3
- **Animation Lab ↗** → opens the visualizer in tab 4

---

## 📊 (Optional) Evaluation numbers for the thesis

Not in the UI — run via curl. `<pid>` is any project you've uploaded materials into. You can grab the auto-generated one from the browser's DevTools → Application → localStorage → `baylearn:pid`, or upload with a manual URL:

```bash
# Single RAGAS run
curl -X POST "http://localhost:8000/api/v1/nlp/evaluate/<pid>?batch_size=5&dataset=cv"

# Ablation study — compares baseline vs +multi_query vs +hybrid vs +reranker vs full
curl -X POST "http://localhost:8000/api/v1/nlp/evaluate/ablation/<pid>" \
  -H "Content-Type: application/json" \
  -d '{"runs":["baseline","multi_query","hybrid","reranker","full"],"batch_size":5,"dataset":"cv"}'
```

---

## 🧯 Troubleshooting (the errors you actually hit)

| Error                                                              | Cause + fix                                                                                                                                                                                                                                                                    |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `npm error ENOENT ... package.json` inside _Linked List Animation_ | It's a **static HTML site**, no npm. Use `python -m http.server 3001` (tab 4 command above).                                                                                                                                                                                   |
| `streamlit run app.py` → "File does not exist"                     | Wrong folder or wrong command. Use `python run.py ui` from `equation-module/` (tab 3).                                                                                                                                                                                         |
| `uvicorn app:app --port 8000` → "Could not import module 'app'"    | The equation module's app is `baylearn.api:app` not `app:app`. Use tab 2's command.                                                                                                                                                                                            |
| Input-parsing: `Attribute "app" not found in module "app"`         | Module is `app.main:app`, not `app:app`. Use tab 1's command.                                                                                                                                                                                                                  |
| `ERROR: pip's dependency resolver ... numpy 2.0.2` during install  | You installed into `base` (or the wrong conda env) — the message shows gensim / contourpy / langchain losing their numpy version. **Deactivate and redo inside `baylearn-parsing`**: `conda deactivate && conda activate baylearn-parsing && pip install -r requirements.txt`. |
| Frontend server dot is red                                         | Tab 5 not running, or `CORS_ORIGINS` in `src/.env` doesn't include `http://localhost:5173`.                                                                                                                                                                                    |
| `/modules/health` shows `equation.available=false`                 | Tab 2 isn't running, or `EQUATION_MODULE_URL` in `src/.env` isn't `http://localhost:9001`.                                                                                                                                                                                     |
| `/modules/health` shows `animation.available=false`                | **Expected** — static visualizer has no `/health`. Don't fix it.                                                                                                                                                                                                               |
| Chat returns "equation module is not running" (503)                | Tab 2 (FastAPI on 9001) isn't up. Starting the Streamlit UI (tab 3) is not enough.                                                                                                                                                                                             |
| Upload returns 413                                                 | File > `UPLOAD_MAX_MB_*` in `src/.env`.                                                                                                                                                                                                                                        |
| Upload returns 422                                                 | Extension not in `_EXT_CATEGORY` in `src/routes/input_parsing.py`.                                                                                                                                                                                                             |
| Intent always classifies as `rag_only`                             | LLM key missing or invalid in `src/.env`. Check orchestrator log — the router falls back silently.                                                                                                                                                                             |

---

## 🧠 Quick mental model

```
  Browser (5173)
       │
       ▼
  Orchestrator (8000)  ←── you run in tab 5 from src/
       │
       ├──► Input-parsing (8100)   ←── tab 1 from Input-Parsing-Module/
       ├──► Equation API  (9001)   ←── tab 2 from equation-module/
       └──► Qdrant Cloud

  + separate tabs the user opens from the sidebar:
       ├──► Equation Streamlit UI (8501)  ←── tab 3
       └──► Linked List Visualizer (3001) ←── tab 4
```

- **Uploads** flow: browser → 8000 → 8100 → Qdrant.
- **Chat** flow: browser → 8000 → (intent classifier) → either Qdrant-only, or also 9001 for equations.
- **Sidebar buttons**: open 8501 / 3001 directly in a new tab (no orchestrator involved).
