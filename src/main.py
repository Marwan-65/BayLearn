import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from fastapi import FastAPI
from repositories.json_chunk_repository import JsonChunkRepository
from helpers.config import get_settings
from stores.LLM.LLMProviderFactory import LLMProviderFactory
from stores.LLM.LLMEnums import LLMEnum, LLMBackendEnum
from stores.vectordb.VectorDBProviderFactory import VectorDBProviderFactory
from routes import base, data, nlp
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()
app.add_middleware( CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
    )
@app.on_event("startup")
async def startup_span():
    settings = get_settings()

    # ── Persistent chunk repository (survives restarts) ──────────────
    # WHY JsonChunkRepository instead of InMemoryChunkRepository?
    # InMemory loses all data on restart. Json persists to disk.
    app.chunk_repository = JsonChunkRepository(
        storage_path="chunks_storage.json"
    )

    # ── LLM Factory ──────────────────────────────────────────────────
    llm_factory = LLMProviderFactory(config=settings)

    # Generation client
    app.generation_client = llm_factory.create(settings.GENERATION_BACKEND)

    if settings.GENERATION_BACKEND == LLMBackendEnum.LOCAL.value:
        generation_model_name = settings.GENERATION_MODEL_ID.lower()
        if generation_model_name == LLMEnum.LLAMA_2.value:
            model_path = "models/llama-2-7b-chat.Q4_K_M.gguf"
        elif generation_model_name == LLMEnum.MISTRAL.value:
            model_path = "models/mistral-7b-instruct.Q4_K_M.gguf"
        else:
            raise ValueError(f"Unsupported local model: {generation_model_name}")
        app.generation_client.set_generation_model(model_id=model_path)

    elif settings.GENERATION_BACKEND == LLMBackendEnum.GROQ.value:
        app.generation_client.set_generation_model(
            model_id=settings.GENERATION_MODEL_ID
        )

    # Embedding client
    app.embedding_client = llm_factory.create(LLMBackendEnum.LOCAL.value)
    app.embedding_client.set_embedding_model(
        model_id=settings.EMBEDDING_MODEL_ID,
        embedding_size=settings.EMBEDDING_MODEL_SIZE,
    )

    # Vector DB client
    vectordb_factory = VectorDBProviderFactory(config=settings)
    app.vectordb_client = vectordb_factory.create(
        provider=settings.VECTOR_DB_BACKEND
    )
    app.vectordb_client.connect()


@app.on_event("shutdown")
async def shutdown_span():
    app.vectordb_client.disconnect()

app.include_router(base.base_router)
app.include_router(data.data_router)
app.include_router(nlp.nlp_router)