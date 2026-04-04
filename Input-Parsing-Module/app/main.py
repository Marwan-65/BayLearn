from fastapi import FastAPI
from .controllers.upload_controller import router
from .config import load_environment

load_environment()

app = FastAPI(title="Input Parsing Module")

app.include_router(router)


