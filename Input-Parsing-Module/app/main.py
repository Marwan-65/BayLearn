from fastapi import FastAPI
from .controllers.upload_controller import router

app = FastAPI(title="Input Parsing Module")

app.include_router(router)


