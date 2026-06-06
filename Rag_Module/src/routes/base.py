from fastapi import  APIRouter, Depends
from helpers.config import get_settings,Settings

base_router = APIRouter(
    prefix="/api/v1",
)

@base_router.get("/")
async def Welcome(app_settings: Settings = Depends(get_settings)):
    app_name = app_settings.APP_NAME
    app_version = app_settings.APP_VERSION
    return f"Welcome to FastAPI {app_name},{app_version}!"