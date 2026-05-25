from fastapi import FastAPI
from .controllers.upload_controller import router
from .config import load_environment

load_environment()

app = FastAPI(title="Input Parsing Module")


@app.get("/health")
async def health():
    return {"status": "healthy", "module": "input-parsing"}


app.include_router(router)


