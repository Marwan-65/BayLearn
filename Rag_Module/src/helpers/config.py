from pydantic_settings import BaseSettings
from typing import Optional
class Settings(BaseSettings):
    APP_NAME: str
    APP_VERSION: str
    GENERATION_BACKEND: str
    EMBEDDING_BACKEND: str
    GROQ_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    GENERATION_MODEL_ID: Optional[str] = None
    GEMINI_MODEL_ID: Optional[str] = "gemini-2.5-flash"
    EMBEDDING_MODEL_ID: Optional[str] = None
    EMBEDDING_MODEL_SIZE: Optional[int] = None
    INPUT_DEFAULT_MAX_CHARACTERS: Optional[int] = 10000
    GENERATION_DEFAULT_MAX_TOKENS: Optional[int] = 1024
    GENERATION_DEFAULT_TEMPERATURE: Optional[float] = 0.1
    VECTOR_DB_BACKEND: Optional[str] = None
    VECTOR_DB_PATH: Optional[str] = None
    VECTOR_DB_DISTANCE_METHOD: Optional[str] = None
    COMPRESSION_ENABLED: Optional[bool] = True
    COMPRESSION_SIMILARITY_THRESHOLD: Optional[float] = 0.3
    COMPRESSION_MIN_KEEP_RATIO: Optional[float] = 0.4
    COMPRESSION_MIN_CHUNK_LENGTH: Optional[int] = 200
    COMPRESSION_SKIP_SINGLE_CHUNK: Optional[bool] = True
    COMPRESSION_RETRIEVAL_MULTIPLIER: Optional[int] = 2
    RERANKER_ENABLED: Optional[bool] = False
    RERANKER_BACKEND: Optional[str] = "CROSS_ENCODER"
    RERANKER_MODEL_ID: Optional[str] = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    RERANKER_OVER_RETRIEVAL_MULTIPLIER: Optional[int] = 3
    MULTI_QUERY_ENABLED: Optional[bool] = True
    MULTI_QUERY_COUNT: Optional[int] = 3
    HYDE_ENABLED: Optional[bool] = False
    HYDE_MAX_TOKENS: Optional[int] = 200
    STRICT_GROUNDING: Optional[bool] = False
    CONTEXTUAL_RETRIEVAL_ENABLED: Optional[bool] = True
    CONTEXTUAL_RETRIEVAL_MAX_TOKENS: Optional[int] = 100
    EQUATION_MODULE_URL: Optional[str] = None
    ANIMATION_MODULE_URL: Optional[str] = None
    INPUT_PARSING_MODULE_URL: Optional[str] = None
    UPLOAD_MAX_MB_PDF: Optional[int] = 50
    UPLOAD_MAX_MB_IMAGE: Optional[int] = 20
    UPLOAD_MAX_MB_AUDIO: Optional[int] = 200
    UPLOAD_MAX_MB_VIDEO: Optional[int] = 1024  
    UPLOAD_MAX_MB_DEFAULT: Optional[int] = 25
    BM25_ENABLED: Optional[bool] = True
    BM25_BACKEND: Optional[str] = "IN_MEMORY"
    BM25_INDEX_DIR: Optional[str] = "bm25_db"
#as K1 increases the effect of term frequency
    BM25_K1: Optional[float] = 1.5
    BM25_B: Optional[float] = 0.75
# but smaller k favors top-ranked documents more strongly
    RRF_K: Optional[int] = 60
    HYBRID_OVER_RETRIEVAL_MULTIPLIER: Optional[int] = 2

    SAME_PAGE_IMAGE_PROMOTION: Optional[bool] = True
    SAME_PAGE_IMAGE_MAX: Optional[int] = 2
    SAME_PAGE_IMAGE_NEIGHBOR_RADIUS: Optional[int] = 2
    SAME_PAGE_IMAGE_NEIGHBORS_PER_IMAGE: Optional[int] = 2
    IMAGE_PROMOTION_MIN_SIMILARITY: Optional[float] = 0.40
    class Config:
        env_file = ".env"
        extra = "ignore"
def get_settings():
    return Settings()
