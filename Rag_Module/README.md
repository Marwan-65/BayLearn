# RAG Module

This is the retrieval-augmented-generation backend for BayLearn. It takes the
study material a student uploads, indexes it, and answers questions grounded in
that material. It also acts as the orchestrator for the other modules (input
parsing, equation solver, animation), so the frontend really only talks to this
service.

The code lives under `src/`. For setup and the exact run commands see
`src/README.md` and `src/RUN.md` — this file is just the map of how things fit
together.

## What it does

Two main jobs:

1. **Ingest** a file. We don't parse anything here. The file is forwarded to the
   Input Parsing Module, which parses it and saves the chunks to the shared DB.
   We then read those chunks back and build the search indexes (Qdrant for dense
   vectors, BM25 for keyword search).

2. **Answer** a question. A question goes through an intent check first (is this a
   normal question, or something that should go to the equation solver?), then
   through the retrieval pipeline, then to the LLM for the final answer.

The DB is the single source of truth for chunks. There is no local copy kept
around for the live app — the old JSON repository is only used by the offline
ablation scripts.

## Layout

```
src/
  main.py            app startup, proxy routes to the other modules
  routes/            HTTP endpoints
    input_parsing.py   upload + index a file (calls the adapter, then indexes)
    nlp.py             /ask, /index, /evaluate, ablation
    orchestrator.py    proxying + module health
    _nlp_handlers.py   the actual handler logic for the nlp routes
  controllers/       the RAG brain (NLPController, split into mixins)
    _nlp_indexing.py    embed + insert into Qdrant + BM25
    _nlp_retrieval.py   the retrieval pipeline
    _nlp_generation.py  build the answer
    _nlp_extraction.py  pull an equation out of the chunks
    _llm_calls.py       every LLM call + its prompt lives here
    intent_router.py    decides rag vs equation
  services/
    input_parsing_adapter.py   HTTP bridge to the Input Parsing Module + DB
    contextual_cache.py        on-disk cache for contextual descriptions
  stores/            providers for the LLM, vector DB, BM25, reranker
  repositories/      chunk storage abstraction (only used by ablation now)
  evaluation/        RAGAS evaluation
  ablation/          offline ablation experiments
```

The controller is one class (`NLPController`) but it's split across a few mixin
files so each piece stays readable. They get composed together in
`controllers/nlp.py`.

## The retrieval pipeline

When a question comes in, `retrieve_sources()` runs these steps. Most of them
can be turned on or off, which is what the ablation study uses to measure how
much each one actually helps.

- HyDE — generate a short fake answer and search with its embedding instead of
  the raw question
- multi-query — ask the LLM for a few reworded versions of the question
- dense search — embed each variant and search Qdrant
- BM25 — keyword search in parallel
- RRF fusion — merge the dense and BM25 result lists
- rerank — cross-encoder re-scores the merged list
- filter — drop anything below the score threshold or with no usable text
- same-page image promotion — if a figure sits on the same page as a good text
  chunk and its description is close enough to the question, pull it in too
- compression — trim each chunk down to the part that matters for the question

After that, `generate_answer_from_sources()` builds a numbered-source prompt and
calls the model. There are two prompts: a normal tutor prompt for chat, and a
strict grounding prompt used during evaluation so the model can't answer from
its own memory and rescue a weak retrieval config.

## Evaluation

The evaluation and ablation code measures retrieval quality with RAGAS. It runs
through the `/api/v1/nlp/evaluate` and `/evaluate/ablation` endpoints, or the
scripts in `ablation/`. These are offline only and not part of the chat flow.
