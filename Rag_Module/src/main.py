# main file for intializing everything in the pipeline
import os
import sys
from pathlib import Path
# the prompt/LLM-call package lives at the repo root, outside this module
sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ["TOKENIZERS_PARALLELISM"] = "false"
""" we disable it as libraries like hugging face use it so they can cause problems with fast api
problems affect performance and may cause deadlocks 
"""
from fastapi import FastAPI, Request, Response
import httpx #for making http for other services like requests but async
from helpers.config import get_settings
from stores.LLM.LLMProviderFactory import LLMProviderFactory
from stores.LLM.LLMEnums import LLMEnum, LLMBackendEnum
from stores.vectordb.VectorDBProviderFactory import VectorDBProviderFactory
from stores.bm25.BM25ProviderFactory import BM25ProviderFactory
from routes import base, nlp, orchestrator
from routes.input_parsing import input_parsing_router
from services.input_parsing_adapter import InputParsingAdapter
from controllers.intent_router import IntentRouter
from services.contextual_cache import ContextualDescriptionCache
# cors is the thing that allow fe to call backend
from fastapi.middleware.cors import CORSMiddleware
# rate limiting to prevent people from abusing the api
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from core.limiter import limiter

app = FastAPI() #server we use
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)
app.state.limiter = limiter
# here we determine what happens when limit is exceeded.
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.on_event("startup")
async def startup_span():
    settings = get_settings()
    llm_factory = LLMProviderFactory(config=settings)
    # factory design pattern to mange clients instead of putting if statements for each different call
    app.generation_client = llm_factory.create(settings.GENERATION_BACKEND)
    # for local models, we need to specify the path to the GGUF file, but it is not effecient 
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
    app.embedding_client = llm_factory.create(LLMBackendEnum.LOCAL.value)
    app.embedding_client.set_embedding_model(
        model_id=settings.EMBEDDING_MODEL_ID,
        embedding_size=settings.EMBEDDING_MODEL_SIZE,
    )
    vectordb_factory = VectorDBProviderFactory(config=settings)
    app.vectordb_client = vectordb_factory.create(
        provider=settings.VECTOR_DB_BACKEND
    )
    app.vectordb_client.connect()

    #reranker and it is optional,it is optional to make tesing rag easier for ablation
    if getattr(settings, "RERANKER_ENABLED", False):
        from stores.reranker.RerankerProviderFactory import RerankerProviderFactory
        reranker_factory = RerankerProviderFactory(config=settings)
        app.reranker_client = reranker_factory.create(
            provider=settings.RERANKER_BACKEND
        )
    else:
        app.reranker_client = None
    #bm25 client for hybrid sparse retrieval to offer keyword search + the already offered semantic(embeddings)
    bm25_factory = BM25ProviderFactory(config=settings)
    app.bm25_client = bm25_factory.create(provider=settings.BM25_BACKEND)
    #for RAG chat detects user intent to show equation module
    app.intent_router = IntentRouter(app.generation_client)
    #input parsing adapter 
    app.input_parsing_adapter = InputParsingAdapter(
        module_url=getattr(settings, "INPUT_PARSING_MODULE_URL", None),
    )
    #contextual retrieval cache for making LLM-generated contextual descriptions across runs persistent so
    #reindexing a project doesn't re-cost too many LLM calls per input.
    app.contextual_cache = ContextualDescriptionCache(
        storage_path="contextual_cache.json"
    )
@app.on_event("shutdown")
async def shutdown_span():
    app.vectordb_client.disconnect()

@app.api_route("/users/{action}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_users_auth(action: str, request: Request):
    settings = get_settings()
    url = f"{settings.INPUT_PARSING_MODULE_URL}/users/{action}"
    if request.url.query:
        url += f"?{request.url.query}"
    async with httpx.AsyncClient() as client:
        body = await request.body()
        headers = dict(request.headers)
        headers.pop("host", None)
        headers.pop("content-length", None)
        res = await client.request(request.method, url, content=body, headers=headers)
        return Response(
            content=res.content,
            status_code=res.status_code,
            media_type=res.headers.get("content-type")
        )


@app.api_route("/courses", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@app.api_route("/courses/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_courses(request: Request, path: str = ""):
    settings = get_settings()
    url = f"{settings.INPUT_PARSING_MODULE_URL}/courses"
    if path:
        url += f"/{path}"
    if request.url.query:
        url += f"?{request.url.query}"
    async with httpx.AsyncClient() as client:
        body = await request.body()
        headers = dict(request.headers)
        headers.pop("host", None)
        headers.pop("content-length", None)
        res = await client.request(request.method, url, content=body, headers=headers)
        return Response(
            content=res.content,
            status_code=res.status_code,
            media_type=res.headers.get("content-type")
        )


@app.api_route("/files", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@app.api_route("/files/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_files(request: Request, path: str = ""):
    settings = get_settings()
    url = f"{settings.INPUT_PARSING_MODULE_URL}/files"
    if path:
        url += f"/{path}"
    if request.url.query:
        url += f"?{request.url.query}"
    async with httpx.AsyncClient(timeout=120.0) as client:
        body = await request.body()
        headers = dict(request.headers)
        headers.pop("host", None)
        headers.pop("content-length", None)
        res = await client.request(request.method, url, content=body, headers=headers)
        return Response(
            content=res.content,
            status_code=res.status_code,
            media_type=res.headers.get("content-type")
        )


@app.api_route("/upload", methods=["POST", "OPTIONS"])
async def proxy_upload(request: Request):
    settings = get_settings()
    url = f"{settings.INPUT_PARSING_MODULE_URL}/upload"
    if request.url.query:
        url += f"?{request.url.query}"
    async with httpx.AsyncClient(timeout=300.0) as client:
        body = await request.body()
        headers = dict(request.headers)
        headers.pop("host", None)
        headers.pop("content-length", None)
        res = await client.request(request.method, url, content=body, headers=headers)
        return Response(
            content=res.content,
            status_code=res.status_code,
            media_type=res.headers.get("content-type")
        )


@app.api_route("/api/v1/questions", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@app.api_route("/api/v1/questions/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_questions(request: Request, path: str = ""):
    settings = get_settings()
    base_url = getattr(settings, "QUESTION_GEN_MODULE_URL", "http://localhost:8001").rstrip("/")
    url = f"{base_url}/api/v1/questions"
    if path:
        url += f"/{path}"
    if request.url.query:
        url += f"?{request.url.query}"
    async with httpx.AsyncClient(timeout=120.0) as client:
        body = await request.body()
        headers = dict(request.headers)
        headers.pop("host", None)
        headers.pop("content-length", None)
        res = await client.request(request.method, url, content=body, headers=headers)
        return Response(content=res.content, status_code=res.status_code, media_type=res.headers.get("content-type"))


@app.api_route("/session", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@app.api_route("/session/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_session(request: Request, path: str = ""):
    settings = get_settings()
    base_url = getattr(settings, "ADAPTIVE_LEARNING_MODULE_URL", "http://localhost:8002").rstrip("/")
    url = f"{base_url}/session"
    if path:
        url += f"/{path}"
    if request.url.query:
        url += f"?{request.url.query}"
    async with httpx.AsyncClient(timeout=120.0) as client:
        body = await request.body()
        headers = dict(request.headers)
        headers.pop("host", None)
        headers.pop("content-length", None)
        res = await client.request(request.method, url, content=body, headers=headers)
        return Response(content=res.content, status_code=res.status_code, media_type=res.headers.get("content-type"))


@app.api_route("/student", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@app.api_route("/student/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_student(request: Request, path: str = ""):
    settings = get_settings()
    base_url = getattr(settings, "ADAPTIVE_LEARNING_MODULE_URL", "http://localhost:8002").rstrip("/")
    url = f"{base_url}/student"
    if path:
        url += f"/{path}"
    if request.url.query:
        url += f"?{request.url.query}"
    async with httpx.AsyncClient(timeout=120.0) as client:
        body = await request.body()
        headers = dict(request.headers)
        headers.pop("host", None)
        headers.pop("content-length", None)
        res = await client.request(request.method, url, content=body, headers=headers)
        return Response(content=res.content, status_code=res.status_code, media_type=res.headers.get("content-type"))

app.include_router(base.base_router)
app.include_router(nlp.nlp_router)
app.include_router(orchestrator.orchestrator_router)
app.include_router(input_parsing_router)
