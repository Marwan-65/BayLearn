from pydantic_settings import BaseSettings, SettingsConfigDict 
from typing import Optional
# define data specs to some validation on it as you will not make it manually 
class Settings(BaseSettings):
    APP_NAME:str
    APP_VERSION:str
    FILE_ALLOWED_EXTENSIONS:list
    FILE_MAX_SIZE:int
    FILE_CHUNK_SIZE:int

    # Generation / Embedding backends
    GENERATION_BACKEND: str
    EMBEDDING_BACKEND: str
    GROQ_API_KEY: Optional[str] = None

    # Model identifiers
    GENERATION_MODEL_ID: Optional[str] = None
    EMBEDDING_MODEL_ID: Optional[str] = None
    EMBEDDING_MODEL_SIZE: Optional[int] = None

    # Character / token defaults
    INPUT_DEFAULT_MAX_CHARACTERS: Optional[int] = None
    GENERATION_DEFAULT_MAX_TOKENS: Optional[int] = None
    GENERATION_DEFAULT_TEMPERATURE: Optional[float] = None

    # Vector DB
    VECTOR_DB_BACKEND: Optional[str] = None
    VECTOR_DB_PATH: Optional[str] = None
    VECTOR_DB_DISTANCE_METHOD: Optional[str] = None
    
# here we load the .env file to get the environment variables defined in it
    class Config:
        env_file = ".env"
def get_settings():
    return Settings()