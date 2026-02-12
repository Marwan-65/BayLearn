from fastapi import FastAPI, APIRouter, Depends
from helpers.config import get_settings,Settings

base_router = APIRouter(
# this is the prefix for all routes defined in this router, so all routes will start with /api/v1
    prefix="/api/v1",
)
@base_router.get("/")
def Welcome(app_settings: Settings = Depends(get_settings)):
    # app_settings = get_settings()
    app_name = app_settings.APP_NAME
    app_version = app_settings.APP_VERSION
    return f"Welcome to FastAPI {app_name},{app_version}!"