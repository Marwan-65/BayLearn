import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .controllers.upload_controller import router
from .config import load_environment

load_environment()

app = FastAPI(title="Input Parsing Module")

# Serve extracted images so the RAG frontend can render them
_IMG_DIR = "extracted_images"
os.makedirs(_IMG_DIR, exist_ok=True)
app.mount("/images", StaticFiles(directory=_IMG_DIR), name="images")


@app.get("/health")
async def health():
    return {"status": "healthy", "module": "input-parsing"}


app.include_router(router)


