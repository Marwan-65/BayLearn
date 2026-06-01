# Adaptive Quiz Loop — Integration Guide for the RL Team

This describes the adaptive quiz flow we built, how it works end to end, and exactly
what the RL module should do in its loop. Read section 1 first

## 1. The mental model

The RL agent and the student are **two separate actors** connected through the Question
Generation (QG) module. The single most important fact:

> **Generation and answering are two different moments in time, separated by a human.** > `generate` creates a question _now_; the student answers it _later_ (seconds to
> minutes). So correctness **cannot** come back from `generate`.

That's why the loop is **two calls**: you `POST …/generate`, then **separately**
`GET …/answer`. The `answer` call **blocks until the student actually answers** in the
UI, then returns `{correct: true|false}`. This matches what your mock already did with
`GET /answer` — the only difference is it's now the **real** student's result, and it
**waits** for them.

```
   (per question)
RL ── POST /generate {topic, difficulty} ─────▶ QG: generate + mark the question answer as "pending"
RL ── GET  /answer  (BLOCKS for the student) ─▶ QG: wait …
                                                 student answers in the frontend
                                                 frontend records the result
   ◀──────────────────── {answered:true, correct:bool} ───────────────────────────
RL: tracker.update(correct) → choose next (topic, difficulty) → repeat
```

The loop runs at **human pace** — gated by how fast the student answers.

> ⚠️ **Training vs. serving.** These endpoints serve the **trained** policy to a real
> student (one question at a time). **Do NOT train against them** — humans are far too
> slow for thousands of episodes. Keep training on your simulator (`mock_api.py`). Use
> these endpoints only with a real student in the loop.

---

## 2. The flow, step by step

**Base URL:** `http://127.0.0.1:8002/api/v1/questions/adaptive/{session_id}`

`{session_id}` identifies one student's quiz. **`default` is a placeholder session id** —
fine for a single-student demo. For multiple students, use a unique id per student
(the frontend must use the same id).

### Step 0 — Start the session (once, at the beginning)

Tell the QG module **which file(s)** the questions come from and **which question type**
to use for this session.

```bash
curl -X POST http://127.0.0.1:8002/api/v1/questions/adaptive/default/config \
  -H "Content-Type: application/json" \
  -d '{"file_ids":"f501ce97-f2d2-45b0-8772-d3da1c310446","question_type":"mcq"}'
```

- `file_ids`: one id, or several comma-joined (`"id1,id2"`) → questions are drawn from
  all of them. (These are the files the student uploaded and selected; they're chosen at session start.)
- `question_type`: set it **once here** for the whole session. **For the RL flow, use
  `mcq` or `true_false`** (these are deterministically gradable). The session reuses this
  type for every question.
- Response: `{"signal":"ok","session_id":"default","file_ids":"…"}`

### Step 1 — RL requests a question (per loop iteration)

```bash
curl -X POST http://127.0.0.1:8002/api/v1/questions/adaptive/default/generate \
  -H "Content-Type: application/json" \
  -d '{"topic":"tcp","difficulty":"medium"}'
```

- Body is `topic` + `difficulty` (`easy` | `medium` | `hard`, case-insensitive). You
  don't need to send the question type — the session's type from Step 0 is used.
- On success (`200`) a question is generated and marked "pending" for the student. You
  don't need to read the body; the frontend renders it.
- On failure (`400`) no question was produced for that topic — see §5.

### Step 2 — RL waits for the result (this blocks)

```bash
curl http://127.0.0.1:8002/api/v1/questions/adaptive/default/answer
```

- **Blocks** until the student answers (long-poll, ~55s max), then returns:
  - `{"answered": true, "correct": true}` or `{"answered": true, "correct": false}`
  - `{"answered": false, "correct": null}` if no answer within the window → **call it
    again** (§4).

### Step 3 — RL updates and loops

Use `correct` to update your tracker, choose the next `(topic, difficulty)`, go to Step 1.

_(Behind the scenes: the student sees the question because the frontend polls
`GET …/current`, and the answer reaches you because the frontend reports it to the QG
module with the `session_id`. Neither is your concern.)_

---

## 3. What the RL module should do (concrete)

```python
QUESTION_API_URL = "http://localhost:5000/generate"
ANSWER_API_URL   = "http://localhost:5000/answer"
```

Point them at the real QG module + a session id, and add a config call at session start:

```python
SESSION = "default"   # placeholder; one id per student
BASE = f"http://127.0.0.1:8002/api/v1/questions/adaptive/{SESSION}"
CONFIG_API_URL   = f"{BASE}/config"
QUESTION_API_URL = f"{BASE}/generate"
ANSWER_API_URL   = f"{BASE}/answer"
```

Your `api_send_question(topic, difficulty)` already POSTs `{topic, difficulty}` ✅, and
`api_get_answer()` already reads `["correct"]` ✅. **The one change you must add:** handle
the long-poll timeout so a slow student isn't recorded as "wrong":

```python
import requests, time

def start_session(file_ids, question_type="mcq"):   # call once at session start
    requests.post(CONFIG_API_URL,
                  json={"file_ids": file_ids, "question_type": question_type},
                  timeout=30).raise_for_status()

def api_send_question(topic, difficulty):
    r = requests.post(QUESTION_API_URL,
                      json={"topic": topic, "difficulty": difficulty}, timeout=60)
    r.raise_for_status()        # 400/500 → no question; retry or pick another topic (§5)

def api_get_answer(max_wait_seconds=600):
    """Block until the student answers; returns True/False. Re-polls on timeout."""
    deadline = time.time() + max_wait_seconds
    while time.time() < deadline:
        data = requests.get(ANSWER_API_URL, timeout=120).json()
        if data.get("answered"):
            return bool(data["correct"])
        # answered == False → 55s window elapsed, student still thinking → re-poll
    raise TimeoutError("Student did not answer in time")
```

Loop (unchanged in spirit):

```python
start_session(file_ids="f501ce97-...", question_type="mcq")   # once
while studying:
    concept, difficulty = policy.choose()
    api_send_question(concept, difficulty)   # POST /generate
    correct = api_get_answer()               # GET /answer (blocks for the student)
    policy.update(concept, difficulty, int(correct))
```

---

## 4. Polling / long-polling — how it works (so you trust it)

- **`GET /answer` is a long-poll.** You send **one** request; the server holds it open
  and internally checks "did the student answer yet?" every 0.5s against an in-memory
  store (no DB, no network), returning the instant the answer arrives or after ~55s.
  **You are not spamming requests** — it's one held-open request, like a slow function
  call. (Your old `timeout=60` matches this; we suggest 120.)
- **The ~55s cap** exists because HTTP connections shouldn't be held open forever. If
  the student is slower, you get `{answered:false}` and simply **call again** (the loop
  in §3). Even a very slow student is only a few re-polls per question — never a flood.
- **The frontend** is the only side doing _short_ polling — `GET …/current` every ~1.5s
  to notice your new question. That's the browser's job, it's cheap, and it does **not**
  involve you.
- **Order-independent:** you may call `/answer` before or after the student answers. If
  they already answered, it returns immediately; otherwise it waits.

---

## 5. What RL should handle on its side

1. **Configure before generating.** Call `/config` (Step 0) before the first
   `/generate`. If you generate first you get `400 "Session not configured…"`.
2. **Re-poll on `{answered:false}`** — don't treat a timeout as "wrong" (§3).
3. **`session_id` must match the frontend's** (single student → `default`).
4. **`/generate` can return `400`.** The QG module runs a question-quality check and
   occasionally produces no valid question for a topic. Treat a non-200 from `/generate`
   as "retry / pick another topic," not a crash.
5. **One pending question at a time** — generate → wait for its answer → generate next.
   Don't fire multiple `/generate` calls before the previous is answered (a new one
   overwrites the pending question).
6. **Question type** is set at session start and reused. To change it, call `/config`
   again. Use `mcq` or `true_false` for the RL loop.

---

## 6. What we changed elsewhere (context — no action needed from RL)

So you understand the system you plug into:

- **Question Generation (8002):** added the adaptive endpoints above + an in-memory
  session store; added server-side answer grading that the frontend uses to report the
  student's answer with the `session_id` — that's what releases your `/answer` long-poll.
- **Input Parsing (8100):** fixed file uploads so parsed files persist to the shared
  database (default-user seeding, a DB column, a DB keep-alive fix). This makes "the
  student's files" exist for generation.
- **RAG (8000):** files are indexed **per file** (each in its own searchable collection)
  with chunks read from the shared database, so a quiz can be scoped to the exact
  file(s) chosen at `/config`.
- **Frontend:** file selection, Adaptive mode (renders your question, reports answers),
  server-side grading.

Net effect for you: the files + type are chosen at `/config`, and **you drive
`generate` → `answer`.** Everything between your two calls (showing the question,
collecting and grading the answer) is handled by the frontend + QG module.

---

## 7. TL;DR for the RL team

1. Once per session: `POST /config {file_ids, question_type}` (use `mcq` or `true_false`).
2. Per question: `POST /generate {topic, difficulty}` → `GET /answer` (blocks) →
   `update(correct)`.
3. `/answer` returns `{answered, correct}`; on `{answered:false}` **re-poll** (don't
   record as wrong).
4. Handle `400` from `/generate` (retry / another topic). Keep `session_id` matching the
   frontend (`default` for one student).
5. This serves a real student, human-paced — keep RL **training** on the simulator.
