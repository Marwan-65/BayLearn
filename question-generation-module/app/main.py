from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.llm.groq_client import QuestionGenLLMClient
from app.services.chunk_fetcher import ChunkFetcher
from app.services.question_service import QuestionGenerationService
from app.routes.question_routes import question_router

app = FastAPI(
    title="BayLearn — Question Generation Module",
    description="Generates quiz questions from indexed study material.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    settings = get_settings()

    # Create the LLM client (calls Groq)
    llm_client = QuestionGenLLMClient(
        api_key=settings.GROQ_API_KEY,
        model_id=settings.GROQ_MODEL_ID,
    )

    # Create the chunk fetcher (calls the RAG module)
    chunk_fetcher = ChunkFetcher(rag_module_url=settings.RAG_MODULE_URL)

    # Create the main service and attach it to the app so routes can access it
    app.question_service = QuestionGenerationService(
        llm_client=llm_client,
        chunk_fetcher=chunk_fetcher,
    )


app.include_router(question_router)