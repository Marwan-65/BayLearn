from pydantic_settings import BaseSettings 
# define data specs to some validation on it
class Settings(BaseSettings):
    APP_NAME:str
    APP_VERSION:str
    FILE_ALLOWED_EXTENSIONS:list
    FILE_MAX_SIZE:int
# here we load the .env file to get the environment variables defined in it
    class Config:
        env_file = ".env"
def get_settings():
    return Settings()