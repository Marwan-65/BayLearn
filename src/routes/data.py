from fastapi import APIRouter,FastAPI,Depends,UploadFile
from helpers.config import get_settings,Settings

data_router = APIRouter(
    prefix="/api/v1",
)
@data_router.get("/upload/{project_id}")
def get_data(project_id: str, file: UploadFile, app_settings: Settings = Depends(get_settings)):
   # validate the file properties but as it is logic will be in controllers directory
    return 