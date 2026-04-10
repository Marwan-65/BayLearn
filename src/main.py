import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"
"""
    Libraries like HuggingFace tokenizers use multi-threading.
    This sometimes causes: warnings , deadlocks in async apps (like FastAPI)
    So this avoids performance/debugging issues.
"""
from fastapi import FastAPI
from repositories.json_chunk_repository import JsonChunkRepository
from helpers.config import get_settings
from stores.LLM.LLMProviderFactory import LLMProviderFactory
from stores.LLM.LLMEnums import LLMEnum, LLMBackendEnum
from stores.vectordb.VectorDBProviderFactory import VectorDBProviderFactory
from routes import base, data, nlp, orchestrator
from routes.input_parsing import input_parsing_router

# CORS middleware (allow frontend to call API)
from fastapi.middleware.cors import CORSMiddleware

# Rate limiting (protect API from abuse)
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from core.limiter import limiter

app = FastAPI()

# React (3000) , Vite (5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.limiter = limiter
# here we define what happens when limit is exceeded.
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.on_event("startup")
async def startup_span():
    settings = get_settings()

    # ── Persistent chunk repository (survives restarts) ──────────────
    app.chunk_repository = JsonChunkRepository(
        storage_path="chunks_storage.json"
    )

    # ── LLM Factory ──────────────────────────────────────────────────
    llm_factory = LLMProviderFactory(config=settings)

    # ── Generation client ─────────────────────────────────────────────
    app.generation_client = llm_factory.create(settings.GENERATION_BACKEND)
    # For local models, we need to specify the path to the GGUF file.
    if settings.GENERATION_BACKEND == LLMBackendEnum.LOCAL.value:
        generation_model_name = settings.GENERATION_MODEL_ID.lower()
        if generation_model_name == LLMEnum.LLAMA_2.value:
            model_path = "models/llama-2-7b-chat.Q4_K_M.gguf"
        elif generation_model_name == LLMEnum.MISTRAL.value:
            model_path = "models/mistral-7b-instruct.Q4_K_M.gguf"
        else:
            raise ValueError(f"Unsupported local model: {generation_model_name}")
        app.generation_client.set_generation_model(model_id=model_path)
    # For cloud models, we just need to specify the model ID (e.g., "gpt-3.5-turbo").
    elif settings.GENERATION_BACKEND == LLMBackendEnum.GROQ.value:
        app.generation_client.set_generation_model(
            model_id=settings.GENERATION_MODEL_ID
        )

    # ── Embedding client ──────────────────────────────────────────────
    app.embedding_client = llm_factory.create(LLMBackendEnum.LOCAL.value)
    app.embedding_client.set_embedding_model(
        model_id=settings.EMBEDDING_MODEL_ID,
        embedding_size=settings.EMBEDDING_MODEL_SIZE,
    )

    # ── Vector DB client ──────────────────────────────────────────────
    vectordb_factory = VectorDBProviderFactory(config=settings)
    app.vectordb_client = vectordb_factory.create(
        provider=settings.VECTOR_DB_BACKEND
    )
    app.vectordb_client.connect()

    # ── Reranker (optional) ───────────────────────────────────────────
    if getattr(settings, "RERANKER_ENABLED", False):
        from stores.reranker.RerankerProviderFactory import RerankerProviderFactory
        reranker_factory = RerankerProviderFactory(config=settings)
        app.reranker_client = reranker_factory.create(
            provider=settings.RERANKER_BACKEND
        )
    else:
        app.reranker_client = None

    # ── BM25 client (hybrid sparse retrieval) ─────────────────────────
    """Traditional keyword search.
    Why: Hybrid retrieval: semantic (embeddings) + lexical (BM25)
    """
    from stores.bm25.BM25ProviderFactory import BM25ProviderFactory
    bm25_factory = BM25ProviderFactory(config=settings)
    app.bm25_client = bm25_factory.create(provider=settings.BM25_BACKEND)

    # ── Intent Router (for RAG chat -> module detection) Detects user intent ──────────────
    from controllers.intent_router import IntentRouter
    app.intent_router = IntentRouter(app.generation_client)

    # ── Input Parsing Adapter ────────────────────────────────
    from services.input_parsing_adapter import InputParsingAdapter
    app.input_parsing_adapter = InputParsingAdapter(
        module_url=getattr(settings, "INPUT_PARSING_MODULE_URL", None),
    )


@app.on_event("shutdown")
async def shutdown_span():
    app.vectordb_client.disconnect()


app.include_router(base.base_router)
app.include_router(data.data_router)
app.include_router(nlp.nlp_router)
app.include_router(orchestrator.orchestrator_router)
app.include_router(input_parsing_router)
