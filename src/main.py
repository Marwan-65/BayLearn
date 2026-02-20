from fastapi import FastAPI
from routes import base, data
# from motor.motor_asyncio import AsyncIOMotorClient   # Commented out for local mock
from helpers.config import get_settings
from stores.llm.LLMProviderFactory import LLMProviderFactory
from stores.llm.LLMEnums import LLMEnum, LLMBackendEnum, ChatRoleEnum

app = FastAPI()


@app.on_event("startup")
async def startup_db_client():
    settings = get_settings()

    # ================= MOCK MongoDB =================
    class MockDB:
        def __getitem__(self, item):
            return self
    app.db_client = MockDB()
    app.mongo_conn = MockDB()
    # ===============================================

    # Initialize LLM factory
    llm_factory = LLMProviderFactory(config=settings)

    # 🔹 Generation client
    app.generation_client = llm_factory.create(LLMBackendEnum.LOCAL.value)

    generation_model_name = settings.GENERATION_MODEL_ID.lower()
    if generation_model_name not in [LLMEnum.LLAMA_2.value, LLMEnum.MISTRAL.value]:
        raise ValueError(
            f"Unsupported generation model: {generation_model_name}. Must be 'llama2' or 'mistral'."
        )
    app.generation_client.set_generation_model(model_id=generation_model_name)

    # 🔹 Embedding client
    app.embedding_client = llm_factory.create(LLMBackendEnum.LOCAL.value)
    app.embedding_client.set_embedding_model(
        model_id=settings.EMBEDDING_MODEL_ID,
        embedding_size=settings.EMBEDDING_MODEL_SIZE,
    )


@app.on_event("shutdown")
async def shutdown_db_client():
    # No real MongoDB, skip closing
    pass


# Routers
app.include_router(base.base_router)
app.include_router(data.data_router)