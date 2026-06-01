from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .controllers.upload_controller import router
from .controllers.course_controller import router as course_router
from .config import load_environment
from app.models.database import create_tables
from .controllers.user_controller import router as user_router


load_environment()

app = FastAPI(title="Input Parsing Module")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    create_tables()
    seed_default_user()

@app.get("/health")
async def health():
    return {"status": "healthy", "module": "input-parsing"}

app.include_router(user_router)
app.include_router(router)
app.include_router(course_router)