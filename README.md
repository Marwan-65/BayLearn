# BayLearn: Adaptive Learning & Verified Tutorial Ecosystem

BayLearn is an open-source, AI-powered intelligent tutoring ecosystem designed for undergraduate engineering curricula. It addresses two structural problems in modern engineering education: the fragmentation of heterogeneous study materials across disparate formats, and the unreliability (mathematical hallucinations) of general-purpose Large Language Models (LLMs) in technical problem-solving.

The platform provides an end-to-end processing pipeline that ingests multimodal course materials, indexes them into a vector space, and drives a suite of adaptive, mathematically verified, and visually interactive tutoring modules.

## System Architecture

BayLearn is composed of six tightly integrated, decoupled subsystems communicating via well-defined data schemas:


```

[Raw Multimodal Input: PDF, Audio, Video, Scans]
│
▼
┌───────────────────────────────┐
│     Input Parsing Module      │ (Hybrid OCR Cascade / Whisper)
└───────────────┬───────────────┘
│ ParsedContent Schema
▼
┌───────────────────────────────┐
│   Retrieval & Indexing Layer  │ (Multi-Query / Hybrid BM25+Dense / RRF)
└───────────────┬───────────────┘
│ Chunks & Embeddings
┌──────────────┼──────────────┐
▼              ▼              ▼
┌─────────────┐┌─────────────┐┌─────────────┐
│ RAG Tutor   ││ Question Gen││ Adaptive RL │ (PFA Tracker / PFA-EPPO Policy)
└─────────────┘└──────┬──────┘└─────────────┘
│
▼
┌─────────────┐
│ BloomBERT   │ (Difficulty Classifier & Verifier)
└─────────────┘
│
┌──────────────┴──────────────┐
▼                             ▼
┌─────────────┐               ┌─────────────┐
│ SymPy Engine│ (Neuro-Sym.)  │ D3.js Engine│ (Deterministic Animation)
└─────────────┘               └─────────────┘

```

## Core Modules

### 1. Adaptive Learning Module (RL Engine)
Acts as the personalization controller, orchestrating individualized, knowledge-diagnostic study sessions.
* **Knowledge Tracing:** Employs a calibrated Performance Factor Analysis (PFA) Tracker with per-difficulty-level parameters ($\gamma_k, \rho_k, \beta_k$) calibrated on the real-world DBE-KT22 dataset.
* **Cross-Concept Generalization:** Incorporates a cosine-similarity graph over `bge-base-en-v1.5` embeddings to propagate partial mastery signals across related concepts without requiring direct testing.
* **Policy Optimization:** Utilizes an on-policy **Proximal Policy Optimization (PPO)** agent (Entropic PPO / EPPO) operating over a joint Cartesian action space of concepts and difficulty levels ($\mathcal{C}_s \times \{0, 1, 2\}$).
* **Warm-Start Mechanism:** Bypasses cold-start exploration traps by pre-training the actor network via Behavioral Cloning (BC) cross-entropy loss on expert student trajectories.

### 2. Algorithm Animation & Visualization Engine
A deterministic, client-side execution engine that renders interactive, step-by-step animations of complex data structures and OS algorithms (B-Trees, Linked Lists, CPU Schedulers).
* **Pre-Computation Memento Model:** To guarantee zero-latency bidirectional navigation ("Step Back/Forward") without recomputation overhead, the algorithm logic runs as pure, side-effect-free functions generating an immutable array of state snapshots (`Step` objects).
* **Decoupled Orchestration:** Implements a strict separation of concerns using GoF behavioral patterns: pure layout and timing plans (`Command`), execution state custody (`Memento`), and synchronized narrative panel updates (`Observer`).
* **Document-Driven Automation:** Integrates an LLM classification and extraction pipeline to automatically parse arbitrary uploaded lecture slides into runnable algorithm operation arrays.

### 3. Input Parsing & Ingestion Pipeline
A multi-engine extraction cascade that converts arbitrary source files into a unified document-section-chunk schema (`ParsedContent`).
* **Tiered OCR Cascade:** Classifies PDF pages spatially as digital or scanned. Scanned media routes through a rate-limited, fault-tolerant cascade: **Gemini Vision API $\rightarrow$ Groq Vision (Llama 4 Scout) $\rightarrow$ Local PaddleOCR (PP-OCRv4)**.
* **Audio/Video Ingestion:** Extracts audio channels via `FFmpeg` (16kHz, mono PCM) and transcribes continuous speech using a local **OpenAI Whisper (large-v3)** model, applying temporal paragraph-grouping heuristics.
* **Structural Preservations:** Pre-processes pages with `img2table` to extract tabular data into Markdown/HTML layouts rather than flattened text arrays.

### 4. Retrieval-Augmented Generation (RAG) Module
A conversational AI assistant grounded strictly in the user's indexed materials.
* **Production Retrieval Pipeline:** Combines Multi-Query expansion (RAG-Fusion) with Hybrid BM25 sparse lexical search and dense vector retrieval (`bge-small-en-v1.5`).
* **Rank Fusion & Reranking:** Merges disparate candidate lists using Reciprocal Rank Fusion (RRF), followed by joint query-document relevance scoring via a `ms-marco-MiniLM` Cross-Encoder.
* **Contextual Compression:** Filters chunk payloads down to query-relevant sentences prior to generation, strictly preserving structural dependencies (equations, tables).

### 5. Question Generation & Assessment Module
Produces difficulty-controlled practice assessments aligned with Bloom’s Taxonomy.
* **Difficulty Classification (BloomBERT):** Fine-tunes a `distilbert-base-uncased` backbone on expert-labeled engineering question banks using **Focal Loss** ($\gamma=2.0$) and label smoothing to overcome severe class imbalance on difficult questions.
* **In-Context Grounding:** Prompts the generation engine with difficulty-indexed, few-shot demonstrations retrieved from a pre-embedded vector space (`all-MiniLM-L6-v2`).
* **Semantic Verification Gate:** Passes all outputs through five algorithmic validators (SBERT anchoring, BM25 answer overlap, distractor cosine matrices, Flesch reading ease, structural invariants) before releasing them to the user.

### 6. Equation & Graph Explanation Module
A neuro-symbolic reasoning system providing absolute mathematical verification.
* **Clean Decomposition:** Delegates natural language intent parsing to a neural LLM (Semantic Stage), while offloading all computational evaluations entirely to the **SymPy** symbolic math engine (Deterministic Stage).
* **Hallucination-Free Pedagogy:** Generates step-by-step pedagogical narratives and D3 visual plots directly from verified symbolic execution traces, eliminating the risk of unverified LLM narrative generation.

## Performance Benchmarks & Verification

* **Question Generation:** The BloomBERT classifier achieved a test macro-F1 of **0.730** (Focal Loss + Label Smoothing), significantly lifting hard-class classification accuracy over standard cross-entropy baselines. Blinded LLM-as-a-Judge evaluations demonstrate a **100% win rate** for difficulty-keyed In-Context Learning over zero-shot baselines across cognitive depth and reasoning criteria.
* **Adaptive Learning:** In multi-session simulated trials across student archetypes (Operating Systems curriculum), the **PFA-EPPO agent outperformed all baselines** (Greedy, Spaced-Repetition, Random, and Rule-based Curriculum), achieving a terminal Full-Course Average Performance Rate (APR) of **0.79–0.83** and accelerating the time-to-breadth mastery by up to 50%.
* **Retrieval Optimization:** Ablation studies on dense single-domain engineering corpora confirm that the hybrid BM25+RRF configuration maximized factual grounding faithfulness (**0.943**), while Cross-Encoder reranking uniquely improved top-$k$ retrieval recall.

## Tech Stack

* **Machine Learning & NLP:** Python 3.10, PyTorch, Hugging Face Transformers (`DistilBERT`, `DeBERTa-v3`), Sentence-Transformers, OpenAI Whisper, SciPy, Scikit-learn.
* **Vector & Data Storage:** Qdrant / ChromaDB (Dense Vectors), BM25 (Sparse Index), SQLite / PostgreSQL (Relational State).
* **Computer Vision & Ingestion:** PyMuPDF (`fitz`), PaddleOCR, Google Gemini Vision API, Groq Vision API, `img2table`, `FFmpeg`.
* **Symbolic Math & Visualization:** SymPy, D3.js, HTML5/SVG, vanilla JavaScript.
* **Backend Microservices:** FastAPI, Flask, Uvicorn, Asynchronous I/O (`asyncio`).

## Startup Instructions
* Configure Environment Variables: Copy ⁠.env.example⁠ to ⁠.env⁠ in each module

* Add your ⁠GROQ_API_KEY⁠ and ⁠GEMINI_API_KEY⁠ where required
* In the terminal run: make all


## License

All rights reserved. Developed at the Department of Computer Engineering, Faculty of Engineering, Cairo University.



