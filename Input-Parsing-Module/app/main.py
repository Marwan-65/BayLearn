from fastapi import FastAPI
from .controllers.upload_controller import router
from .config import load_environment
from app.models.database import create_tables

load_environment()

app = FastAPI(title="Input Parsing Module")

@app.on_event("startup")
def startup():
    create_tables()

@app.get("/health")
async def health():
    return {"status": "healthy", "module": "input-parsing"}


app.include_router(router)


