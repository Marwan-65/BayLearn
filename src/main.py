from fastapi import FastAPI
from mock.seed_data import seed_project
from repositories.in_memory_chunk_repository import InMemoryChunkRepository
from routes import base, data, nlp
# from motor.motor_asyncio import AsyncIOMotorClient   # Commented out for local mock
from helpers.config import get_settings
from stores.LLM.LLMProviderFactory import LLMProviderFactory
from stores.LLM.LLMEnum import LLMEnum, LLMBackendEnum
from stores.vectordb.VectorDBProviderFactory import VectorDBProviderFactory

app = FastAPI()

@app.on_event("startup")
async def startup_span():
    settings = get_settings()

    # ================= MOCK MongoDB =================
    chunk_repository = InMemoryChunkRepository()
    await seed_project(chunk_repository)
    app.chunk_repository = chunk_repository
    # ===============================================

    # Initialize LLM factory
    llm_factory = LLMProviderFactory(config=settings)
    vectorDBProviderFactory = VectorDBProviderFactory(config=settings)  
    
    # Generation client
    app.generation_client = llm_factory.create(LLMBackendEnum.LOCAL.value)
    generation_model_name = settings.GENERATION_MODEL_ID.lower()
    if generation_model_name not in [LLMEnum.LLAMA_2.value, LLMEnum.MISTRAL.value]:
        raise ValueError(
            f"Unsupported generation model: {generation_model_name}. Must be 'llama2' or 'mistral'."
        )
    app.generation_client.set_generation_model(model_id=generation_model_name)

    # Embedding client
    app.embedding_client = llm_factory.create(LLMBackendEnum.LOCAL.value)
    app.embedding_client.set_embedding_model(
        model_id=settings.EMBEDDING_MODEL_ID,
        embedding_size=settings.EMBEDDING_MODEL_SIZE,
    )
    
    # vector db client
    app.vectordb_client = vectorDBProviderFactory.create(provider=settings.VECTOR_DB_BACKEND)
    app.vectordb_client.connect() 
    
@app.on_event("shutdown")
async def shutdown_span():
    # No real MongoDB, skip closing
    app.vectordb_client.disconnect()  # Disconnect vector DB client if needed

# Routers
app.include_router(base.base_router)
app.include_router(data.data_router)
app.include_router(nlp.nlp_router)