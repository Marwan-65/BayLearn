from fastapi import APIRouter,FastAPI,Depends,UploadFile
from helpers.config import get_settings,Settings
from controllers import data

data_router = APIRouter(
    prefix="/api/v1",
)
@data_router.get("/upload/{project_id}")
async def upload_file(project_id: str, file: UploadFile, app_settings: Settings = Depends(get_settings)):
# validate the file properties but as it is logic will be in controllers directory
    is_valid,result_signal = data.validate_file(file=file)
    return {
        "is_valid": is_valid,
        "result_signal": result_signal
    }