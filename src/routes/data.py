from fastapi import APIRouter,FastAPI,Depends,UploadFile, status
from fastapi.responses import JSONResponse
from helpers.config import get_settings,Settings
from controllers import DataController , ProjectController
import aiofiles
import os
from models import Response_Signal

data_router = APIRouter(
    prefix="/api/v1",
)
@data_router.post("/upload/{project_id}")
async def upload_file(project_id: str, file: UploadFile , app_settings: Settings = Depends(get_settings)):
# validate the file properties but as it is logic will be in controllers directory
    is_valid,result_signal = DataController().validate_file(file=file)
    if not is_valid:
        
        return JSONResponse(
            status_code= status.HTTP_400_BAD_REQUEST,
            content={"message": result_signal}
        )
    project_dir=ProjectController().make_project_dir(project_id=project_id)
    print(f"Project directory: {project_dir}")
    project_dir_path = os.path.join(project_dir, file.filename)
    async with aiofiles.open(project_dir_path,"wb") as f :
        while chunk := await file.read(app_settings.FILE_CHUNK_SIZE):
            await f.write(chunk)
    
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": Response_Signal.FILE_UPLOAD_SUCCESS.value}
    )
        