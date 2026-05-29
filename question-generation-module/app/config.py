from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    GROQ_API_KEY: str = "your_groq_api_key_here"
    GROQ_MODEL_ID: str = "llama3-8b-8192"
    RAG_MODULE_URL: str = "http://localhost:8000"

    class Config:
        env_file = ".env"
# Call this function wherever you need settings
def get_settings() -> Settings:
  return Settings()