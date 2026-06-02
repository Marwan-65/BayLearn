from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    GROQ_API_KEY: str = "your_groq_api_key_here"
    GROQ_MODEL_ID: str = "llama-3.3-70b-versatile"
    RAG_MODULE_URL: str = "http://localhost:8000"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL_ID: str = "gemini-2.0-flash"
    LLM_PROVIDER: str = "groq"

    class Config:
        env_file = ".env"
        extra = "ignore"
# Call this function wherever you need settings
def get_settings() -> Settings:
  return Settings()