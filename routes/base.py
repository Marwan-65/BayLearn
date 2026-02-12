from fastapi import FastAPI, APIRouter
# we use os to access environment variables
import os

base_router = APIRouter(
# this is the prefix for all routes defined in this router, so all routes will start with /api/v1
    prefix="/api/v1",
)
@base_router.get("/")
def Welcome():
    app_name = os.getenv("APP_NAME")
    app_version = os.getenv("APP_VERSION")
    return f"Welcome to FastAPI {app_name},{app_version}!"