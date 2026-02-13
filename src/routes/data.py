from fastapi import APIRouter,FastAPI,Depends,UploadFile, status
from fastapi.responses import JSONResponse
from helpers.config import get_settings,Settings
from controllers import data

data_router = APIRouter(
    prefix="/api/v1",
)
@data_router.get("/upload/{project_id}")
async def upload_file(project_id: str, file: UploadFile, app_settings: Settings = Depends(get_settings)):
# validate the file properties but as it is logic will be in controllers directory
    is_valid,result_signal = data.validate_file(file=file)
    if not is_valid:
        return JSONResponse(
            status_code= status.HTTP_400_BAD_REQUEST,
            content={"message": result_signal.value}
        )
        