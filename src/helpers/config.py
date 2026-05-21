from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    APP_NAME: str
    APP_VERSION: str

    # Generation / Embedding backends
    GENERATION_BACKEND: str
    EMBEDDING_BACKEND: str
    GROQ_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    # Model identifiers
    GENERATION_MODEL_ID: Optional[str] = None
    GEMINI_MODEL_ID: Optional[str] = "gemini-2.5-flash"
    EMBEDDING_MODEL_ID: Optional[str] = None
    EMBEDDING_MODEL_SIZE: Optional[int] = None

    # Character / token defaults
    INPUT_DEFAULT_MAX_CHARACTERS: Optional[int] = 10000
    GENERATION_DEFAULT_MAX_TOKENS: Optional[int] = 1024
    GENERATION_DEFAULT_TEMPERATURE: Optional[float] = 0.1

    # Vector DB
    VECTOR_DB_BACKEND: Optional[str] = None
    VECTOR_DB_PATH: Optional[str] = None
    VECTOR_DB_DISTANCE_METHOD: Optional[str] = None

    # Contextual Compression
    COMPRESSION_ENABLED: Optional[bool] = True
    COMPRESSION_SIMILARITY_THRESHOLD: Optional[float] = 0.3
    COMPRESSION_MIN_KEEP_RATIO: Optional[float] = 0.4
    COMPRESSION_MIN_CHUNK_LENGTH: Optional[int] = 200
    COMPRESSION_SKIP_SINGLE_CHUNK: Optional[bool] = True
    COMPRESSION_RETRIEVAL_MULTIPLIER: Optional[int] = 2

    # Reranker
    RERANKER_ENABLED: Optional[bool] = False
    RERANKER_BACKEND: Optional[str] = "CROSS_ENCODER"
    RERANKER_MODEL_ID: Optional[str] = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    RERANKER_OVER_RETRIEVAL_MULTIPLIER: Optional[int] = 3

    # Multi-Query (RAG-Fusion)
    MULTI_QUERY_ENABLED: Optional[bool] = True
    MULTI_QUERY_COUNT: Optional[int] = 3

    # Contextual Retrieval (Anthropic 2024) helps model understand chunk better.
    CONTEXTUAL_RETRIEVAL_ENABLED: Optional[bool] = True
    CONTEXTUAL_RETRIEVAL_MAX_TOKENS: Optional[int] = 100

    # Other Modules' URLs (for orchestrator proxy)
    EQUATION_MODULE_URL: Optional[str] = None
    ANIMATION_MODULE_URL: Optional[str] = None

    # Input Parsing Module URL
    INPUT_PARSING_MODULE_URL: Optional[str] = None

    # Per-type upload size limits (MB). Applied in routes/input_parsing.py
    # based on the uploaded file's extension.
    UPLOAD_MAX_MB_PDF: Optional[int] = 50
    UPLOAD_MAX_MB_IMAGE: Optional[int] = 20
    UPLOAD_MAX_MB_AUDIO: Optional[int] = 200
    UPLOAD_MAX_MB_VIDEO: Optional[int] = 1024  # 1 GB
    UPLOAD_MAX_MB_DEFAULT: Optional[int] = 25

    # BM25 + RRF Hybrid Retrieval
    BM25_ENABLED: Optional[bool] = True
    BM25_BACKEND: Optional[str] = "IN_MEMORY"
    BM25_INDEX_DIR: Optional[str] = "bm25_db"
    # K1 → term frequency importance , Higher → repeated words matter more
    BM25_K1: Optional[float] = 1.5
    BM25_B: Optional[float] = 0.75
    # Small k → top ranks dominate , Large k → smoother ranking
    RRF_K: Optional[int] = 60
    HYBRID_OVER_RETRIEVAL_MULTIPLIER: Optional[int] = 2

    # Same-page image promotion: after text retrieval, also surface image
    # chunks from the same pages so figures get rendered alongside answers.
    SAME_PAGE_IMAGE_PROMOTION: Optional[bool] = True
    SAME_PAGE_IMAGE_MAX: Optional[int] = 2
    # When promoting an image, also pull this many text chunks within
    # ±N chunk-ids of the image so the LLM gets the caption / surrounding
    # paragraph that explains what the figure shows.
    SAME_PAGE_IMAGE_NEIGHBOR_RADIUS: Optional[int] = 2
    SAME_PAGE_IMAGE_NEIGHBORS_PER_IMAGE: Optional[int] = 2
    # Cosine-similarity gate between (image's text description) and (query
    # embedding). Images below this never get promoted, even if they live on
    # the same page as a top text match. Tune higher for stricter relevance,
    # lower for more visual content. 0.30 is a reasonable starting point.
    IMAGE_PROMOTION_MIN_SIMILARITY: Optional[float] = 0.40

    class Config:
        env_file = ".env"


def get_settings():
    return Settings()
