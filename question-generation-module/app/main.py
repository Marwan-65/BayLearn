import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.llm.groq_client import QuestionGenLLMClient
from app.services.chunk_fetcher import ChunkFetcher
from app.services.question_service import QuestionGenerationService
from app.services.example_bank import ExampleBank
from app.services.answer_grader import AnswerGrader
from app.classifier.bloom_classifier import BloomClassifier
from app.routes.question_routes import question_router
from app.routes.adaptive_routes import adaptive_router
from app.services.adaptive_session import AdaptiveSessionStore

logger = logging.getLogger(__name__)
_MODULE_ROOT = Path(__file__).resolve().parents[1]
BLOOM_MODEL_DIR = _MODULE_ROOT / "models" / "bloom_distilbert"
EXAMPLE_BANK_PATH = _MODULE_ROOT / "data" / "processed" / "example_bank.jsonl"

app = FastAPI(
    title="BayLearn — Question Generation Module",
    description="Generates quiz questions from indexed study material with "
                "ICL retrieval + BloomBERT-validated difficulty.",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    # Match any localhost/127.0.0.1 origin on any port (Vite may use 5174+ if 5173
    # is busy, and localhost != 127.0.0.1 to the browser). A fixed allowlist would
    # block the frontend's /questions/generate and /questions/check calls via CORS.
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    settings = get_settings()

    
    llm_client = QuestionGenLLMClient(
        api_key=settings.GROQ_API_KEY,
        model_id=settings.GROQ_MODEL_ID,
    )

    # Chunk fetcher (RAG module)
    chunk_fetcher = ChunkFetcher(rag_module_url=settings.RAG_MODULE_URL)

    # Few-shot example bank (graceful empty if file missing)
    example_bank = ExampleBank.load(EXAMPLE_BANK_PATH)
    logger.info("Example bank stats: %s", example_bank.stats())

    # Answer grader — reuses the example bank's embedder (same MiniLM instance)
    # so short-answer semantic grading costs no extra model memory.
    app.answer_grader = AnswerGrader(embedder=example_bank)

    # In-memory coordination store for the agent-driven adaptive quiz loop.
    app.adaptive_sessions = AdaptiveSessionStore()

    # BloomBERT classifier 
    bloom_classifier = BloomClassifier.load(BLOOM_MODEL_DIR)

    # Service with ICL + classifier validation wired in
    app.question_service = QuestionGenerationService(
        llm_client=llm_client,
        chunk_fetcher=chunk_fetcher,
        example_bank=example_bank,
        bloom_classifier=bloom_classifier,
        few_shot_k=3,
        retry_on_level_mismatch=True,
    )


app.include_router(question_router)
app.include_router(adaptive_router)
