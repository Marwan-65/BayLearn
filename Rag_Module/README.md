# RAG Module

This is the RAG backend for BayLearn. A student uploads study material, we index it, and then we answer their questions from that material. It also works as the orchestrator, so the frontend basically only talks to this service and we forward to the other modules (parsing, equation solver,animation) when a request needs them.
Setup and the exact run commands are in `src/README.md` and `src/RUN.md`. This
file is just the map of how the pieces fit.

## What it actually does

Uploading a file: we don't parse anything ourselves here. The file is forwarded to the Input Parsing Module, which parses it and writes the chunks to the shared DB. We read those chunks back out and build the search indexes from them (Qdrant for the dense vectors, BM25 for keyword search).

Answering a question: there's an intent check first (is this a normal question, or does the student actually want the equation solver to compute something?), then the retrieval pipeline, then the LLM writes the final answer using what we pulled back.

The DB is the single source of truth for chunks. The running app keeps no local copy.

## Folder layout

```
BayLearn/
  RAG_module_models/   prompts + the LLM/judge calls, kept OUTSIDE this module
    llm_calls.py         answer, hyde, multi-query, contextual, equation, intent
    ragas_judges.py      the RAGAS judge models
    chatgroqfixed.py     a small Groq client wrapper
  Rag_Module/src/
    main.py             startup + the proxy routes to the other modules
    core/limiter.py     rate limiting, shared by main and the routers
    routes/
      input_parsing.py   upload a file, then index it
      nlp.py             /ask, /index, /evaluate, ablation endpoints
      orchestrator.py    proxying + module health checks
      _nlp_handlers.py   the handler logic behind the nlp routes
    controllers/        the RAG brain, NLPController split across mixins
      _nlp_indexing.py    embed + push into Qdrant and BM25
      _nlp_retrieval.py   the retrieval pipeline
      _nlp_generation.py  builds the answer
      _nlp_extraction.py  pulls an equation out of the chunks
      intent_router.py    decides rag vs equation
    services/
      input_parsing_adapter.py   http bridge to the parsing module + DB
      contextual_cache.py        on-disk cache so we don't re-pay for descriptions
    stores/             provider wrappers: LLM, vector DB, BM25, reranker
    evaluation/         RAGAS scoring
```

I split NLPController across a few mixin files because one file was getting
impossible to read. They get stitched back together in `controllers/nlp.py`.

The prompts and the raw LLM/judge calls don't live in this module at all. They
sit in a separate `RAG_module_models/` folder at the repo root, and the
controllers and the evaluator just call into it. So the logic files here stay
about retrieval and generation, not about prompt text.

## The retrieval pipeline

`retrieve_sources()` is where most of the work happens. Almost every step has an on/off switch, which is the whole reason the ablation study exists: flip one off and see how far the score drops.

Roughly in order:

- HyDE: write a short fake answer first and search with its embedding instead of the bare question.
- multi-query: ask the LLM for a few reworded versions of the question.
- dense search: embed each version and search Qdrant.
- BM25: keyword search running next to the dense one.
- RRF fusion: merge the dense and BM25 lists into one ranking.
- rerank: a cross-encoder re-scores the merged list.
- filter: drop anything under the score threshold or with no usable text.
- same-page image promotion: if a figure is on the same page as a chunk we kept, and its description is close enough to the question, we pull the figure in too.
- compression: trim each chunk down to the part that's actually relevant.

After that `generate_answer_from_sources()` formats the kept chunks as numbered sources and calls the model. There are two prompts. The normal one is the tutor voice used in chat. The strict one is for evaluation: it forbids outside knowledge, so a weak retrieval config can't get rescued by the model's own memory.

## Evaluation

We measure quality with RAGAS, either through the `/api/v1/nlp/evaluate` and
`/evaluate/ablation` endpoints or the standalone scripts in the evaluation folder.
