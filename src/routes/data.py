from fastapi import APIRouter,FastAPI,Depends,UploadFile, status
from fastapi.responses import JSONResponse
from helpers.config import get_settings,Settings
from controllers import DataController , ProjectController
import aiofiles
import os
from models import Response_Signal
import logging
from services.processing_service import ProcessingService

logger = logging.getLogger("uvicorn.error")
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
    normalized_filename,file_id= DataController().generate_random_filename(filename=file.filename,project_id=project_id)
    project_dir_path = os.path.join(project_dir, normalized_filename)
    # in case an error occurs during file writing, we catch it and return an appropriate response
    # but real causes will be in logs
    try:
        async with aiofiles.open(project_dir_path,"wb") as f :
            while chunk := await file.read(app_settings.FILE_CHUNK_SIZE):
                await f.write(chunk)
    except Exception as e:
        logger.error(f"Error occurred while uploading file: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"message": Response_Signal.FILE_UPLOAD_FAILED.value}
        )
    
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": Response_Signal.FILE_UPLOAD_SUCCESS.value
                ,"file_id": file_id}
    )
@data_router.post("/process/{project_id}")
async def process_file(
    project_id: str,
    request: Request,
    file_id: str,
    app_settings: Settings = Depends(get_settings)
):
    """
    Step 2 of the pipeline: parse an uploaded file into RAG chunks.
    Call this AFTER /upload and BEFORE /nlp/index/push
    """
    file_path = os.path.join(
        ProjectController().make_project_dir(project_id),
        file_id
    )

    if not os.path.exists(file_path):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"message": f"File not found at {file_path}. Did you upload it first?"}
        )

    try:
        processing_service = ProcessingService()
        chunks = processing_service.process_pdf(
            file_path=file_path,
            project_id=project_id
        )
        await request.app.chunk_repository.add_chunks(project_id, chunks)

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": "File processed successfully",
                "chunks_created": len(chunks),
                "project_id": project_id
            }
        )

    except Exception as e:
        logger.error(f"Processing failed: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"message": f"Processing failed: {str(e)}"}
        )       