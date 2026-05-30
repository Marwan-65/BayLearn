# Question Generation Module — Setup Guide

Complete instructions to set up the BloomBERT-validated in-context-learning
question generation pipeline from a fresh clone.

This module is one piece of the larger BayLearn project. It takes content
chunks (from the Input Parsing Module or RAG vector DB), retrieves few-shot
example questions at a target Bloom level, asks an LLM to generate new
questions, and uses a fine-tuned BloomBERT classifier to verify the output
matches the requested difficulty.

---

## 1. Prerequisites

- **macOS, Linux, or WSL** (Windows native untested)
- **Python 3.12** via Anaconda / Miniconda — get it from
  https://docs.conda.io/en/latest/miniconda.html
- **Git** to clone the repo
- **~5 GB free disk** (PyTorch + transformers + datasets)
- **Optional: Kaggle account** if you want to retrain BloomBERT yourself
  (otherwise the trained model is downloaded from a shared link)
- **Optional: Groq API key** for the LLM-generation endpoint
  (the classifier and example bank work fully offline)

---

## 2. Clone and create the environment

```bash
git clone <repo-url> baylearn
cd baylearn/question-generation-module

# Create an isolated conda environment for this module specifically.
# (The RAG module has its own env; do not mix them.)
conda create -n baylearn-qg python=3.12 -y
conda activate baylearn-qg

pip install -r requirements.txt
```

This installs PyTorch 2.5.1, transformers 4.46.3, sentence-transformers,
FastAPI, and supporting libraries with versions pinned to known-working
combinations. Takes 3–5 min.

Verify the install:

```bash
python -c "import torch, transformers, sentence_transformers; \
           print(torch.__version__, transformers.__version__, sentence_transformers.__version__)"
```

Expected: `2.5.1 4.46.3 3.3.1`.

---

## 3. Get the training data

You need three CSV files in `data/processed/`:
`train.csv`, `val.csv`, `test.csv`.

### Option A — Use already-built CSVs (recommended)

If your collaborator shared the `data/processed/` folder, just drop it in.
Skip to Section 4.

### Option B — Rebuild from raw sources

You need three raw inputs:

1. **SRM Valliammai question banks** (PDFs) — download from
   https://srmvalliammai.ac.in/question-banks/
   Place all CS-relevant PDFs (OS, DBMS, Data Structures, Algorithms,
   Networks, Software Engineering, etc.) into
   `data/raw_srm/`.

2. **Devane Kaggle dataset** — install kagglehub if not present, then run:
   ```bash
   python -c "
   import kagglehub, shutil
   p = kagglehub.dataset_download('vijaydevane/blooms-taxonomy-dataset')
   shutil.copy(f'{p}/blooms_taxonomy_dataset.csv', 'data/raw_external/devane.csv')
   print('Devane CSV copied to data/raw_external/devane.csv')
   "
   ```

3. **(Optional) OS eyeball-labeled question bank** — a markdown file with
   questions and your manually-assigned levels. If you have one, parse it:
   ```bash
   python scripts/parse_os_eyeball.py path/to/your/OS_questions.md
   ```

Build the unified train/val/test split (per-source × per-level stratified,
de-duplicated):

```bash
python scripts/parse_srm_question_bank.py     # produces data/processed/srm_questions.csv
python scripts/build_training_set.py          # produces train.csv, val.csv, test.csv
```

Expected output: ~25k train, ~3k val, ~3k test rows.

---

## 4. Train BloomBERT (Kaggle)

Local training on CPU takes >5 hours. Use Kaggle's free T4 GPU instead.

### 4.1 Upload data as a Kaggle dataset

1. Go to https://kaggle.com → Datasets → New Dataset
2. Upload `data/processed/train.csv`, `val.csv`, `test.csv`
3. Set visibility to Private
4. Note the slug — the notebook will reference it as
   `/kaggle/input/<your-slug>/`

### 4.2 Pick a training notebook

Five notebooks live under `notebooks/`:

| Notebook | Test macro-F1 | Description |
|---|---|---|
| `train_bloombert.ipynb` | 0.7261 | Baseline (CE loss, linear, 4 epochs) — includes 1/2/3 layer ablation |
| `train_bloombert_focal.ipynb` | **0.7498** | **Recommended.** Focal loss γ=2, 8 epochs |
| `train_bloombert_focal_cosine.ipynb` | 0.7459 | Adds cosine LR (didn't help) |
| `train_bloombert_focal_meanpool.ipynb` | 0.7475 | Adds mean-pool (didn't help) |
| `train_bloombert_focal_smoothing.ipynb` | 0.7474 | Adds label smoothing (didn't help) |

Open `train_bloombert_focal.ipynb` on Kaggle:
1. File → Import Notebook → upload the `.ipynb`
2. Right-side panel → Add Input → select your dataset
3. Settings → Accelerator → GPU T4 x1
4. Edit Cell 1 if your dataset path differs from the default

Run all cells. ~25 min on T4.

### 4.3 Download the trained model

After training, the final cell zips the output directory. Download
`bloom_distilbert_focal.zip` (~250 MB) from the right-side Output panel.

Locally:

```bash
mkdir -p models
cd models
unzip ~/Downloads/bloom_distilbert_focal.zip -d bloom_distilbert
ls bloom_distilbert/   # should show config.json, model.safetensors, tokenizer files
cd ..
```

The runtime wrapper looks for `models/bloom_distilbert/` by default.

---

## 5. Build the example bank

The few-shot retrieval bank is built from labeled questions (SRM CE
subjects + your optional OS eyeball file):

```bash
python scripts/build_example_bank.py
```

Default: 50 examples per level (150 total) drawn from the full pool.
Output: `data/processed/example_bank.jsonl`.

Embeddings are computed at FastAPI startup the first time the bank is
loaded (takes ~30 sec for 150 entries).

---

## 6. (Optional) Re-label your eyeball OS bank with BloomBERT

If you have an `os_eyeball.csv` file from Section 3, replace your manual
labels with the trained classifier's predictions:

```bash
python scripts/relabel_os_with_bloombert.py
```

Output:
- `data/processed/os_eyeball_relabeled.csv` — your CSV with both labels
  side-by-side and a new authoritative `level` column from BloomBERT
- Agreement report printed to console (eyeball vs model %)

Then refresh the example bank to use the cleaner labels:

```bash
python scripts/build_example_bank.py
```

### Interpret disagreements

For a deeper look at *why* BloomBERT disagrees with your eye:

```bash
python scripts/analyze_relabel_disagreements.py
```

This prints feature averages per disagreement bucket (avg word count,
code presence, math content, sub-part count, verb category) so you can
see what signals the model uses to assign each level. Output also
written to `data/processed/relabel_feature_analysis.csv`.

---

## 7. Run the API server

Create a `.env` file in the module root:

```bash
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL_ID=llama-3.1-70b-versatile
RAG_MODULE_URL=http://localhost:8000
```

(`RAG_MODULE_URL` is where the RAG module is running — set it to whatever
port you started the RAG service on.)

Start the FastAPI server:

```bash
uvicorn app.main:app --reload --port 8001
```

Expected startup log:

```
INFO:     BloomBERT loaded from models/bloom_distilbert on cpu
INFO:     Example bank stats: {'total': 150, 'by_level': {'easy': 50, 'medium': 50, 'hard': 50}, 'by_type': {'short_answer': 150}}
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8001
```

If you see "BloomBERT weights not found at … — running in stub mode" then
the model dir isn't at `models/bloom_distilbert/` — recheck Section 4.3.

### Test the generation endpoint

```bash
curl -X POST http://localhost:8001/generate \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "your-indexed-project-id",
    "num_questions": 3,
    "difficulty": "apply",
    "question_type": "short_answer",
    "topic": "process synchronization"
  }'
```

(`project_id` must be a project already indexed by the RAG module.)

Response includes the generated questions plus each question's
`predicted_level` and `level_confidence` from BloomBERT.

---

## 8. Project structure reference

```
question-generation-module/
├── app/
│   ├── main.py                      FastAPI entry point (startup wires everything)
│   ├── config.py                    Reads .env
│   ├── classifier/
│   │   └── bloom_classifier.py      BloomBERT runtime wrapper
│   ├── services/
│   │   ├── question_service.py      Main generation pipeline
│   │   ├── prompt_builder.py        MCQ / short-answer / true-false prompts with ICL block
│   │   ├── example_bank.py          Few-shot retrieval (embed + cosine + level filter)
│   │   └── chunk_fetcher.py         Pulls chunks from RAG module via HTTP
│   ├── models/
│   │   └── schemas.py               Pydantic request/response models
│   ├── llm/
│   │   └── groq_client.py           Thin Groq API wrapper
│   └── routes/
│       └── question_routes.py       FastAPI route handlers
│
├── data/
│   ├── raw_srm/                     Downloaded SRM PDFs (you provide)
│   ├── raw_external/                Devane Kaggle CSV (auto-downloaded)
│   └── processed/                   Built training set + example bank
│
├── models/
│   └── bloom_distilbert/            Trained BloomBERT weights (download from Kaggle)
│
├── notebooks/                       Kaggle T4 training notebooks
│
├── scripts/                         Data prep + analysis CLI scripts
│
├── requirements.txt                 Pinned dependencies
└── SETUP.md                         This file
```

---

## 9. Troubleshooting

### "BloomBERT weights not found" at startup
The folder `models/bloom_distilbert/` does not exist or is missing
`config.json`. Re-extract the Kaggle zip. The classifier will run in
"stub mode" (returns level=None) if weights are missing; the API still
serves but skips validation.

### "Example bank file not found"
Run `python scripts/build_example_bank.py`. The bank is loaded once at
startup; restart the API after rebuilding.

### `ModuleNotFoundError: No module named 'torch'`
You're using system Python, not the conda env's Python. Run
`conda activate baylearn-qg` first. If `python` still resolves wrong, use
the explicit path:
`/opt/anaconda3/envs/baylearn-qg/bin/python`.

### `tokenizers version mismatch`
You mixed two environments. Recreate the env clean:
```bash
conda deactivate
conda env remove -n baylearn-qg
conda create -n baylearn-qg python=3.12 -y
conda activate baylearn-qg
pip install -r requirements.txt
```

### Kaggle download fails on `model.safetensors` (>200 MB)
Kaggle's per-file browser download can be flaky on large files. The
notebooks save a `.zip` of the whole output directory as the final step —
download that instead. If you forgot the zip step, paste this into a new
cell in your training notebook session:
```python
import shutil, os
zip_path = shutil.make_archive('/kaggle/working/bloom_distilbert', 'zip', OUT_DIR)
print(zip_path, os.path.getsize(zip_path) / 1e6, 'MB')
```

### Generation requests return empty questions
Usually means the RAG module isn't running, or the `project_id` you
passed isn't indexed there. Check `RAG_MODULE_URL` in `.env` matches
where you actually started the RAG service.

---

## 10. Reproducing the published results

If you want bit-for-bit identical numbers to the project report:

| Result | How to reproduce |
|---|---|
| Baseline test macro-F1 = 0.7261 | `train_bloombert.ipynb` with `Config['unfreeze_top']=3`, 4 epochs |
| Ablation 1/2/3 layers (0.7051 / 0.7170 / 0.7261) | Run all cells of `train_bloombert.ipynb`, see `ablation_results.json` |
| Focal final macro-F1 = 0.7498 | `train_bloombert_focal.ipynb` |
| OS bank vs BloomBERT 41.2% agreement | `scripts/relabel_os_with_bloombert.py` against the focal checkpoint |
| Per-bucket feature analysis | `scripts/analyze_relabel_disagreements.py` |

All notebooks use `SEED=42` and pinned hyperparameters so reruns are
deterministic on the same hardware (Kaggle T4).
