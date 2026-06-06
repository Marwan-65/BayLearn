# Question Generation Module

This module makes quiz questions from a student's study material and grades their
answers. It's a FastAPI service. An LLM writes the questions, but we don't trust
the LLM to judge its own difficulty. A fine-tuned BloomBERT classifier checks the
level of every question it writes, so when we label something "easy" it really is
easy.

Two things make the output better than just prompting a model:

ICL (in-context learning): before generating, we pull a few expert example
questions at the requested level out of an example bank and drop them into the
prompt. The model imitates the style and difficulty instead of guessing it.

BloomBERT difficulty check: a DistilBERT model trained on Bloom-taxonomy labels
predicts the level of each generated question. If it doesn't match what was
asked, we can retry.

## Layout

The prompts, the LLM clients, and the BloomBERT model definition do not live
inside this module. They sit in a separate `question_generation_model/` folder at
the repo root, and the app and scripts import from it. So the code you read under
`app/` and `scripts/` stays about the actual logic, not prompt strings or model
wiring.

```
question_generation_model/      (at the repo root, OUTSIDE this module)
  prompt_builder.py     the MCQ / short-answer / true-false prompts
  _gen_llm.py           the generation LLM client
  _judge_llm.py         the LLM-as-judge client + rubric
  llm/                  groq / gemini client wrappers
  bloom_model.py        the BloomBERT model: HF encoder + pooling head + loss
  test_chunks.py        OS passages used by the baseline-vs-ICL experiment
  curated_questions.py  hand-written questions that seed the example bank

question-generation-module/
  app/
    main.py             FastAPI app + startup
    config.py           settings
    routes/
      question_routes.py   /questions/generate, /questions/check
      adaptive_routes.py   adaptive session endpoints
    services/
      question_service.py   the generation flow (fetch examples, prompt, validate)
      example_bank.py       loads + retrieves the few-shot examples
      chunk_fetcher.py      pulls chunks from the parsing/RAG side
      answer_grader.py      grades a student's answer
      semantic_validator.py checks the question is on-topic
      context_enrichment.py extra context for the prompt
      adaptive_session.py   tracks a student's session
    classifier/
      bloom_classifier.py   loads the trained BloomBERT and predicts a level
  scripts/      offline data + evaluation scripts (below)
  notebooks/    train_bloombert.py, the BloomBERT training driver
  models/       the trained bloom_distilbert weights the app loads
  data/         raw + processed datasets, and the built example bank
```

## Running it

```bash
pip install -r requirements.txt
cp .env.example .env    # add GROQ_API_KEY and/or GEMINI_API_KEY
uvicorn app.main:app --port 8001
```

Generation needs two things to already exist: the trained BloomBERT model (under
`models/bloom_distilbert/`) and the example bank. If the bank isn't there yet,
build it:

```bash
python scripts/build_example_bank.py
```

## Scripts (offline, not part of the API)

- `build_example_bank.py` builds the few-shot example bank + embeddings from the
  labeled CSVs and the curated questions.
- `build_training_set.py` assembles the BloomBERT training data.
- `parse_os.py`, `parse_srm.py`, `relabel_os.py` do the dataset prep.
- `generate_baseline_vs_icl.py` generates questions twice per cell (with and
  without the example bank) for the comparison.
- `llm_judge_baseline_vs_icl.py` runs a blinded pairwise LLM-as-judge over those
  generations, counterbalanced so position bias cancels out.
- `difficulty_match_baseline_vs_icl.py` is the judge-free check: it runs BloomBERT
  on every generated question and reports how often the predicted level matches
  the one that was requested.

## Training BloomBERT

`notebooks/train_bloombert.py` is the training driver. The model itself (the
HuggingFace DistilBERT encoder, the pooling head, and the focal/label-smoothing
loss) is kept separate in `question_generation_model/bloom_model.py`, so the
trainer file is purely the tuning part: the hyperparameter configs, the layer-wise
learning-rate decay, the schedule, the training loop, and evaluation. Pick a setup
with `--variant` (base, focal, focal_cosine, focal_smoothing, focal_meanpool,
combined, and so on). Whatever run you save into `models/bloom_distilbert/` is the
one the app loads at startup.
