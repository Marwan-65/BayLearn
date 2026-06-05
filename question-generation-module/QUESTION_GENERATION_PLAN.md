# Question Generation Module — MVP Implementation Plan

> Written for: a student who is learning and building this from scratch.  
> Goal: Build a standalone FastAPI service (just like the Input Parsing Module)
> that takes already-parsed, already-embedded chunks and generates quiz questions from them.

---

## 🗺️ How the Existing Codebase Works (Read This First!)

Before you write a single line, understand what already exists so you **reuse instead of rewrite**.

### The Big Picture

```
[PDF / Video / Image]
        ↓
[Input-Parsing-Module] — already built ✅
  Parses the file, splits into chunks, returns JSON like:
  { "sections": [{ "chunks": [{ "content": "...", "metadata": {...} }] }] }
        ↓
[src/ — the RAG Module] — already built ✅
  Takes those chunks, embeds them (turns text into numbers a computer can compare),
  stores them in a vector database (Qdrant), and answers student questions.
        ↓
[question-generation-module/] — ← YOU ARE BUILDING THIS ⬅️
  Takes the same chunks (or retrieves relevant ones from the vector DB)
  and generates quiz questions from them using an LLM.
```

### Key Files You Will Reuse or Mirror

| File | What it does | How you'll use it |
|------|-------------|-------------------|
| `Input-Parsing-Module/app/models/unified_content_schema.py` | Defines the `ParsedContent` / `Chunk` schema that the parser outputs | Your module receives this same JSON shape as input |
| `src/models/chunk.py` | The `Chunk(chunk_id, text, metadata)` dataclass used by the RAG module | You can reuse this exact shape for reading stored chunks |
| `src/stores/LLM/providers/GroqProvider.py` | Calls the Groq cloud API to generate text | You will call an LLM the same way |
| `src/controllers/_nlp_generation.py` | Shows the exact pattern for building a prompt and calling the LLM | Copy this pattern for your question-generation prompts |
| `src/controllers/_nlp_retrieval.py` | Shows how the RAG module retrieves the most relevant chunks | You can call this (or replicate the vector search) to get chunks relevant to a topic |
| `src/routes/orchestrator.py` | Shows how a new module is registered as a proxy endpoint in the main app | You will add a `/question-gen` proxy the same way |

---

## 🔑 Concepts You Need to Understand

### What is a "chunk"?
A chunk is a small piece of text (a paragraph, a table, a caption) that was extracted from a document.
It looks like this:
```python
Chunk(
    chunk_id=0,
    text="Ohm's law states that V = IR, where V is voltage...",
    metadata={"page": 3, "doc_title": "lecture1.pdf", "chunk_type": "text"}
)
```

### What is a vector / embedding?
An embedding is a list of numbers (e.g., 384 numbers) that represents the *meaning* of a piece of text.
Two sentences that mean the same thing will have similar numbers. This is how the RAG module finds
relevant chunks without exact keyword matching. You **do not need to implement this** — the RAG
module already stores and searches these for you.

### What is Groq?
Groq is a free (with API key) cloud service that runs LLMs (like Llama 3) extremely fast.
You already use it in the RAG module (`src/stores/LLM/providers/GroqProvider.py`).
Your question generation module will use it too — just call it with a prompt that says
"given this text, generate 5 quiz questions".

---

## 📦 Module Structure You Will Build

```
question-generation-module/
├── app/
│   ├── main.py                     ← FastAPI app entry point
│   ├── config.py                   ← Read API keys from .env
│   ├── models/
│   │   └── schemas.py              ← Pydantic models for request/response
│   ├── services/
│   │   └── question_service.py     ← Core logic: takes chunks → returns questions
│   ├── llm/
│   │   └── groq_client.py          ← Thin wrapper around Groq API
│   └── routes/
│       └── question_routes.py      ← FastAPI route handlers
├── requirements.txt
└── .env.example
```

---

## 🪜 Baby Steps — Implement in This Exact Order

---

### STEP 1 — Set Up the Project Skeleton

**What you're doing:** Creating the folder structure and installing dependencies.

**Why first:** You can't run anything without this.

1. Create all the folders listed in the structure above. You can do it manually or with:
   ```bash
   cd question-generation-module
   mkdir -p app/models app/services app/llm app/routes
   touch app/__init__.py app/models/__init__.py app/services/__init__.py app/llm/__init__.py app/routes/__init__.py
   ```

2. Create `requirements.txt` with these contents:
   ```
   fastapi
   uvicorn[standard]
   pydantic
   pydantic-settings
   groq
   python-dotenv
   httpx
   ```

3. Create a virtual environment and install:
   ```bash
   python -m venv venv
   # On Windows:
   .\venv\Scripts\Activate.ps1
   # On Mac/Linux:
   source venv/bin/activate

   pip install -r requirements.txt
   ```

4. Create `.env.example`:
   ```
   GROQ_API_KEY=your_groq_api_key_here
   GROQ_MODEL_ID=llama3-8b-8192
   RAG_MODULE_URL=http://localhost:8003
   ```

5. Copy it to `.env` and fill in your real Groq API key.

**✅ Checkpoint:** You can run `python -c "import fastapi, groq; print('OK')"` without errors.

---

### STEP 2 — Write the Config Reader

**What you're doing:** Writing code that reads your `.env` file so the rest of the app can use the API keys.

**Why:** Every other file will need the API key. You want one central place to read it.

**File:** `app/config.py`

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    GROQ_API_KEY: str
    GROQ_MODEL_ID: str = "llama3-8b-8192"
    RAG_MODULE_URL: str = "http://localhost:8000"

    class Config:
        env_file = ".env"

# Call this function wherever you need settings
def get_settings() -> Settings:
    return Settings()
```

**✅ Checkpoint:** Run `python -c "from app.config import get_settings; print(get_settings().GROQ_MODEL_ID)"` — it should print the model name.

---

### STEP 3 — Write the Request/Response Schemas

**What you're doing:** Defining what your API accepts as input and what it returns as output.

**Why:** FastAPI uses these Pydantic models to automatically validate requests. If someone sends
bad data, FastAPI rejects it before it even reaches your code.

**File:** `app/models/schemas.py`

```python
from pydantic import BaseModel, Field
from typing import List, Optional

# ── What the caller sends to your API ──────────────────────────────────────
class GenerateQuestionsRequest(BaseModel):
    project_id: str = Field(..., description="The ID of the indexed project/document")
    topic: Optional[str] = Field(None, description="Optional: focus questions on a topic")
    num_questions: int = Field(default=5, ge=1, le=20, description="How many questions to generate")
    difficulty: str = Field(default="medium", description="easy | medium | hard")
    question_type: str = Field(default="mcq", description="mcq | short_answer | true_false")

# ── One generated question ─────────────────────────────────────────────────
class QuestionOption(BaseModel):
    label: str          # "A", "B", "C", "D"
    text: str           # "The speed of light"
    is_correct: bool    # True for the correct answer

class GeneratedQuestion(BaseModel):
    question_text: str
    question_type: str  # "mcq", "short_answer", "true_false"
    options: Optional[List[QuestionOption]] = None   # Only for MCQ
    correct_answer: str                              # The answer text
    explanation: str                                 # Why this is correct
    source_chunk_id: Optional[int] = None           # Which chunk this came from
    difficulty: str

# ── What your API returns ──────────────────────────────────────────────────
class GenerateQuestionsResponse(BaseModel):
    project_id: str
    topic: Optional[str]
    questions: List[GeneratedQuestion]
    total_generated: int
    chunks_used: int    # How many source chunks were used
```

**✅ Checkpoint:** Run `python -c "from app.models.schemas import GenerateQuestionsRequest; print('OK')"`.

---

### STEP 4 — Write the Groq LLM Wrapper

**What you're doing:** Writing a small class that calls the Groq API to generate text.

**Why:** You isolate all LLM communication in one place. If you ever switch to a different LLM,
you only change this file.

**Look at this for reference:** `src/stores/LLM/providers/GroqProvider.py` — yours will be simpler.

**File:** `app/llm/groq_client.py`

```python
import logging
from groq import Groq

logger = logging.getLogger(__name__)

class QuestionGenLLMClient:
    """
    Thin wrapper around the Groq API for text generation.
    Mirrors the pattern in src/stores/LLM/providers/GroqProvider.py
    but only does generation (no embeddings needed here).
    """

    def __init__(self, api_key: str, model_id: str):
        self.model_id = model_id
        self.client = Groq(api_key=api_key)

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """
        Send a prompt to Groq and return the generated text.
        
        system_prompt: Instructions for how the LLM should behave
        user_prompt: The actual task (e.g., "generate questions from this text")
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Groq generation failed: {e}")
            raise
```

**✅ Checkpoint:** You can import the class. (Don't call it yet — you need the full service for that.)

---

### STEP 5 — Write the Chunk Fetcher

**What you're doing:** Writing code to fetch relevant chunks from the RAG module (the `src/` app).

**Why:** You don't want to duplicate the vector search logic. The RAG module already has it.
You just call its `/api/v1/nlp/index/search/{project_id}` endpoint.

**How the RAG module's search endpoint works:**
- Method: `POST`
- URL: `http://localhost:8000/api/v1/nlp/index/search/{project_id}`
- Body: `{ "text": "your topic here", "limit": 10 }`
- Returns: `{ "top_results": [{ "id": 0, "score": 0.87, "payload": { "text": "...", "page": 1 } }] }`

**File:** `app/services/chunk_fetcher.py`

```python
import httpx
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

FETCH_TIMEOUT = 30.0

class ChunkFetcher:
    """
    Fetches relevant text chunks from the RAG module's vector search API.
    
    Instead of re-implementing embedding + vector search, we call the
    already-built RAG module at src/. This is the Adapter pattern —
    the same one used in src/services/input_parsing_adapter.py.
    """

    def __init__(self, rag_module_url: str):
        self.rag_module_url = rag_module_url.rstrip("/")

    async def fetch_relevant_chunks(
        self,
        project_id: str,
        query: str,
        limit: int = 10,
    ) -> List[dict]:
        """
        Call the RAG module's search endpoint to get text chunks
        semantically related to `query`.

        Returns a list of dicts, each with:
            - "id": chunk_id (int)
            - "score": relevance score (float, 0-1)
            - "payload": { "text": "...", "page": 1, ... }
        """
        url = f"{self.rag_module_url}/api/v1/nlp/index/search/{project_id}"
        payload = {"text": query, "limit": limit}

        try:
            async with httpx.AsyncClient(timeout=FETCH_TIMEOUT) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("top_results", [])
        except httpx.ConnectError:
            logger.error(f"RAG module unreachable at {self.rag_module_url}")
            raise ConnectionError("RAG module is not running. Start it first.")
        except httpx.HTTPStatusError as e:
            logger.error(f"RAG module returned {e.response.status_code}")
            raise RuntimeError(f"RAG module error: {e.response.status_code}")
```

**✅ Checkpoint:** Import the class, no errors.

---

### STEP 6 — Write the Prompt Builder

**What you're doing:** Writing the prompts you send to the LLM to make it generate questions.

**Why a separate file:** Prompts are complex and you will iterate on them many times.
Keeping them separate from the service logic makes them easy to find and tweak.

**Look at this for reference:** `src/controllers/_nlp_generation.py` — see how it builds a `system_prompt` + `user_prompt`.

**File:** `app/services/prompt_builder.py`

```python
from typing import List

def build_mcq_prompt(chunks_text: str, num_questions: int, difficulty: str) -> tuple[str, str]:
    """
    Returns (system_prompt, user_prompt) for MCQ generation.
    
    chunks_text: All retrieved chunk texts joined together
    """
    system_prompt = (
        "You are an expert university professor who creates high-quality quiz questions.\n"
        "You ONLY generate questions based on the provided study material — never from general knowledge.\n"
        "Output ONLY valid JSON. No extra text, no markdown code blocks.\n"
    )

    user_prompt = f"""
Generate exactly {num_questions} multiple choice questions at {difficulty} difficulty from the study material below.

STUDY MATERIAL:
{chunks_text}

OUTPUT FORMAT — return a JSON array, nothing else:
[
  {{
    "question_text": "What does Ohm's law state?",
    "options": [
      {{"label": "A", "text": "V = IR", "is_correct": true}},
      {{"label": "B", "text": "V = I/R", "is_correct": false}},
      {{"label": "C", "text": "V = I + R", "is_correct": false}},
      {{"label": "D", "text": "V = IR²", "is_correct": false}}
    ],
    "correct_answer": "V = IR",
    "explanation": "Ohm's law defines the relationship between voltage, current and resistance.",
    "difficulty": "{difficulty}"
  }}
]

Generate {num_questions} questions now:
"""
    return system_prompt, user_prompt


def build_short_answer_prompt(chunks_text: str, num_questions: int, difficulty: str) -> tuple[str, str]:
    system_prompt = (
        "You are an expert university professor creating short-answer exam questions.\n"
        "Base all questions ONLY on the provided study material.\n"
        "Output ONLY valid JSON. No extra text.\n"
    )

    user_prompt = f"""
Generate exactly {num_questions} short-answer questions at {difficulty} difficulty from the study material below.

STUDY MATERIAL:
{chunks_text}

OUTPUT FORMAT — return a JSON array, nothing else:
[
  {{
    "question_text": "What is the relationship between voltage, current, and resistance?",
    "correct_answer": "V = IR (Ohm's law): voltage equals current times resistance.",
    "explanation": "This is the fundamental equation in circuit analysis.",
    "difficulty": "{difficulty}"
  }}
]

Generate {num_questions} questions now:
"""
    return system_prompt, user_prompt


def build_true_false_prompt(chunks_text: str, num_questions: int, difficulty: str) -> tuple[str, str]:
    system_prompt = (
        "You are an expert university professor creating true/false quiz questions.\n"
        "Base all questions ONLY on the provided study material.\n"
        "Output ONLY valid JSON. No extra text.\n"
    )

    user_prompt = f"""
Generate exactly {num_questions} true/false questions at {difficulty} difficulty from the study material below.

STUDY MATERIAL:
{chunks_text}

OUTPUT FORMAT — return a JSON array, nothing else:
[
  {{
    "question_text": "Ohm's law states that voltage equals current divided by resistance.",
    "correct_answer": "False",
    "explanation": "Ohm's law states V = IR (voltage = current × resistance, not divided).",
    "difficulty": "{difficulty}"
  }}
]

Generate {num_questions} questions now:
"""
    return system_prompt, user_prompt
```

**✅ Checkpoint:** You can call `build_mcq_prompt("some text", 3, "medium")` and get back two strings.

---

### STEP 7 — Write the Core Question Service

**What you're doing:** Writing the main logic that ties everything together:
1. Fetch relevant chunks (Step 5)
2. Build a prompt (Step 6)
3. Call the LLM (Step 4)
4. Parse the JSON response into your schemas (Step 3)

**File:** `app/services/question_service.py`

```python
import json
import logging
from typing import List, Optional

from question_generation_model.llm.groq_client import QuestionGenLLMClient
from app.services.chunk_fetcher import ChunkFetcher
from question_generation_model.prompt_builder import (
    build_mcq_prompt,
    build_short_answer_prompt,
    build_true_false_prompt,
)
from app.models.schemas import GeneratedQuestion, QuestionOption

logger = logging.getLogger(__name__)

# Max characters of chunk text to include in a single prompt.
# Groq models have a context limit — don't exceed it.
MAX_CONTEXT_CHARS = 6000


class QuestionGenerationService:
    """
    Core service for generating quiz questions from study material.

    Flow:
        fetch relevant chunks from RAG module
            → build LLM prompt
                → call Groq
                    → parse JSON response
                        → return GeneratedQuestion list
    """

    def __init__(self, llm_client: QuestionGenLLMClient, chunk_fetcher: ChunkFetcher):
        self.llm_client = llm_client
        self.chunk_fetcher = chunk_fetcher

    async def generate(
        self,
        project_id: str,
        num_questions: int,
        difficulty: str,
        question_type: str,
        topic: Optional[str] = None,
    ) -> tuple[List[GeneratedQuestion], int]:
        """
        Generate questions for a project.

        Returns: (list of GeneratedQuestion, number_of_chunks_used)
        """
        # 1. Decide what to search for
        search_query = topic if topic else "key concepts definitions important principles"

        # 2. Fetch relevant chunks from the RAG module
        raw_chunks = await self.chunk_fetcher.fetch_relevant_chunks(
            project_id=project_id,
            query=search_query,
            limit=10,
        )

        if not raw_chunks:
            raise ValueError(f"No indexed content found for project '{project_id}'. "
                             "Make sure the project has been uploaded and indexed first.")

        # 3. Join chunk texts, but don't exceed the LLM context limit
        chunks_text = self._prepare_context(raw_chunks)

        # 4. Build prompt based on question type
        if question_type == "mcq":
            system_prompt, user_prompt = build_mcq_prompt(chunks_text, num_questions, difficulty)
        elif question_type == "short_answer":
            system_prompt, user_prompt = build_short_answer_prompt(chunks_text, num_questions, difficulty)
        elif question_type == "true_false":
            system_prompt, user_prompt = build_true_false_prompt(chunks_text, num_questions, difficulty)
        else:
            raise ValueError(f"Unknown question_type: {question_type}. Use mcq, short_answer, or true_false.")

        # 5. Call the LLM
        raw_response = self.llm_client.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.7,
        )

        # 6. Parse the JSON the LLM returned
        questions = self._parse_llm_response(raw_response, question_type)

        return questions, len(raw_chunks)

    def _prepare_context(self, raw_chunks: list) -> str:
        """
        Join chunk texts into a single string for the prompt.
        Truncate to MAX_CONTEXT_CHARS to avoid hitting LLM limits.
        """
        parts = []
        total_chars = 0

        for chunk in raw_chunks:
            text = chunk.get("payload", {}).get("text", "")
            if not text:
                continue
            if total_chars + len(text) > MAX_CONTEXT_CHARS:
                # Add a partial chunk so we don't waste space
                remaining = MAX_CONTEXT_CHARS - total_chars
                parts.append(text[:remaining])
                break
            parts.append(text)
            total_chars += len(text)

        return "\n\n---\n\n".join(parts)

    def _parse_llm_response(self, raw_response: str, question_type: str) -> List[GeneratedQuestion]:
        """
        Parse the JSON array the LLM returned into GeneratedQuestion objects.

        The LLM sometimes wraps JSON in markdown code fences like ```json ... ```
        This method handles that gracefully.
        """
        # Strip markdown code fences if present
        text = raw_response.strip()
        if text.startswith("```"):
            # Remove first line (```json or ```) and last line (```)
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"LLM returned invalid JSON: {e}\nRaw response: {raw_response[:500]}")
            raise ValueError("The LLM returned malformed JSON. Try again.")

        questions = []
        for item in data:
            # Build options list only for MCQ
            options = None
            if question_type == "mcq" and "options" in item:
                options = [
                    QuestionOption(
                        label=opt["label"],
                        text=opt["text"],
                        is_correct=opt.get("is_correct", False),
                    )
                    for opt in item.get("options", [])
                ]

            questions.append(GeneratedQuestion(
                question_text=item.get("question_text", ""),
                question_type=question_type,
                options=options,
                correct_answer=item.get("correct_answer", ""),
                explanation=item.get("explanation", ""),
                difficulty=item.get("difficulty", "medium"),
            ))

        return questions
```

**✅ Checkpoint:** Import the class, no errors.

---

### STEP 8 — Write the FastAPI Route

**What you're doing:** Exposing your service as an HTTP endpoint so the main BayLearn backend
(and eventually the frontend) can call it.

**Look at this for reference:** `Input-Parsing-Module/app/controllers/` and `src/routes/nlp.py`.

**File:** `app/routes/question_routes.py`

```python
import logging
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.models.schemas import GenerateQuestionsRequest, GenerateQuestionsResponse

logger = logging.getLogger(__name__)

question_router = APIRouter(prefix="/api/v1/questions", tags=["Question Generation"])


@question_router.post("/generate")
async def generate_questions(
    body: GenerateQuestionsRequest,
    request: Request,
):
    """
    Generate quiz questions from an indexed project's study material.
    
    Requires the RAG module to be running and the project to be indexed first.
    """
    service = request.app.question_service  # set in startup (see main.py)

    try:
        questions, chunks_used = await service.generate(
            project_id=body.project_id,
            num_questions=body.num_questions,
            difficulty=body.difficulty,
            question_type=body.question_type,
            topic=body.topic,
        )
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"signal": str(e)},
        )
    except ConnectionError as e:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"signal": str(e)},
        )
    except Exception as e:
        logger.error(f"Question generation failed: {e}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"signal": "Internal error during question generation."},
        )

    response = GenerateQuestionsResponse(
        project_id=body.project_id,
        topic=body.topic,
        questions=questions,
        total_generated=len(questions),
        chunks_used=chunks_used,
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response.model_dump(),
    )


@question_router.get("/health")
async def health_check():
    """Health check endpoint — the orchestrator in src/ will call this."""
    return JSONResponse(status_code=200, content={"status": "ok"})
```

**✅ Checkpoint:** Import the router, no errors.

---

### STEP 9 — Write the FastAPI App Entry Point

**What you're doing:** Wiring everything together into a runnable FastAPI app.

**Look at this for reference:** `src/main.py` — how it creates the app, registers routes, and sets
up clients in `startup`.

**File:** `app/main.py`

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from question_generation_model.llm.groq_client import QuestionGenLLMClient
from app.services.chunk_fetcher import ChunkFetcher
from app.services.question_service import QuestionGenerationService
from app.routes.question_routes import question_router

app = FastAPI(
    title="BayLearn — Question Generation Module",
    description="Generates quiz questions from indexed study material.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    settings = get_settings()

    # Create the LLM client (calls Groq)
    llm_client = QuestionGenLLMClient(
        api_key=settings.GROQ_API_KEY,
        model_id=settings.GROQ_MODEL_ID,
    )

    # Create the chunk fetcher (calls the RAG module)
    chunk_fetcher = ChunkFetcher(rag_module_url=settings.RAG_MODULE_URL)

    # Create the main service and attach it to the app so routes can access it
    app.question_service = QuestionGenerationService(
        llm_client=llm_client,
        chunk_fetcher=chunk_fetcher,
    )


app.include_router(question_router)
```

**✅ Checkpoint:** Run the server with:
```bash
cd question-generation-module
uvicorn app.main:app --reload --port 8002
```
Open `http://localhost:8002/docs` — you should see the Swagger UI with your endpoint listed.

---

### STEP 10 — Test It End-to-End

**What you're doing:** Actually calling your API and checking the output.

**Before testing:**
1. Make sure the Input Parsing Module is running on port 8000 (or whatever port it uses).
2. Make sure the RAG module (`src/`) is running.
3. Make sure a document has been uploaded and indexed.

**Test with curl (from the terminal):**

```bash
curl -X POST "http://localhost:8002/api/v1/questions/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "your_project_id_here",
    "topic": "electric circuits",
    "num_questions": 3,
    "difficulty": "medium",
    "question_type": "mcq"
  }'
```

**Expected response shape:**
```json
{
  "project_id": "...",
  "topic": "electric circuits",
  "questions": [
    {
      "question_text": "What does Ohm's law state?",
      "question_type": "mcq",
      "options": [
        {"label": "A", "text": "V = IR", "is_correct": true},
        ...
      ],
      "correct_answer": "V = IR",
      "explanation": "...",
      "difficulty": "medium"
    }
  ],
  "total_generated": 3,
  "chunks_used": 10
}
```

**✅ Checkpoint:** You get back a JSON array of real questions from your study material.

---

### STEP 11 — Register the Module in the Main Orchestrator

**What you're doing:** Adding a proxy endpoint in `src/routes/orchestrator.py` so the BayLearn
frontend can call the question generation module through the main API.

**Look at this for reference:** How `equation_run` and `animation_run` are implemented in
`src/routes/orchestrator.py`.

1. **Add the URL to settings** — in `src/.env`, add:
   ```
   QUESTION_GEN_MODULE_URL=http://localhost:8002
   ```

2. **Add the proxy endpoint** — in `src/routes/orchestrator.py`, add:
   ```python
   @orchestrator_router.post("/question-gen/generate")
   @limiter.limit("20/minute")
   async def question_gen_run(request: Request, run_request: dict):
       settings = get_settings()
       base_url = getattr(settings, "QUESTION_GEN_MODULE_URL", None)
       url_error = _check_module_url("QuestionGen", base_url)
       if url_error:
           return url_error
       try:
           result = await _proxy_post(base_url, "/api/v1/questions/generate", run_request)
           return JSONResponse(status_code=status.HTTP_200_OK, content=result)
       except Exception as e:
           return _handle_proxy_error("QuestionGen", base_url, e)
   ```

3. **Also add it to the health check** in the `modules_health` endpoint:
   ```python
   "question_gen": getattr(settings, "QUESTION_GEN_MODULE_URL", None),
   ```

**✅ Checkpoint:** Calling `POST http://localhost:8000/api/v1/question-gen/generate` with the
same body returns the same questions.

---

### STEP 12 — Error Handling & Edge Cases

**What you're doing:** Making your code robust against things going wrong.

Go through each file and handle these cases:

| Scenario | Where it happens | What to do |
|----------|-----------------|------------|
| LLM returns empty string | `question_service.py` | Raise `ValueError("LLM returned empty response")` |
| LLM returns invalid JSON even after stripping fences | `question_service.py` `_parse_llm_response` | Retry once, then raise |
| RAG module is not running | `chunk_fetcher.py` | Already handled — `ConnectionError` is raised and caught in the route |
| Project has no indexed content | `question_service.py` | Already handled — `ValueError` |
| `num_questions` > actual parseable items | `question_service.py` | Return however many questions were generated, don't crash |
| LLM generates fewer questions than requested | `question_service.py` | Accept the partial result, log a warning |

---

## 🧠 Glossary (Quick Reference)

| Term | Simple Explanation |
|------|-------------------|
| **Chunk** | A small piece of text from a document (a paragraph or section). |
| **Embedding / Vector** | A list of numbers representing the meaning of a text. Similar meanings = similar numbers. |
| **Vector DB (Qdrant)** | A database that stores these number-lists and can find the most similar ones quickly. |
| **RAG** | Retrieval-Augmented Generation: find relevant chunks first, then ask the LLM to use them. |
| **BM25** | Old-school keyword search (like Google's early algorithm). Used alongside vector search. |
| **Groq** | A free cloud service to run LLMs fast. You send it a prompt, it sends back generated text. |
| **FastAPI** | The Python web framework used throughout this project. |
| **Pydantic** | Python library for data validation. `BaseModel` subclasses are the schemas. |
| **Adapter Pattern** | A design pattern where you write a wrapper to make two incompatible interfaces work together. |
| **Project ID** | A string identifying a document collection that has been uploaded and indexed in the RAG module. |

---

## ⚡ Quick Cheat Sheet — Startup Order

Every time you work on this:

```
Terminal 1:  cd Input-Parsing-Module && uvicorn app.main:app --port 8000 --reload
Terminal 2:  cd src && python -m uvicorn main:app --port 8001 --reload  (or whatever port)
Terminal 3:  cd question-generation-module && uvicorn app.main:app --port 8002 --reload
```

(Check the README.md files in each module for the exact commands.)
