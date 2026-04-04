from fastapi import APIRouter, UploadFile, File
from app.services.parsing_service import ParsingService


router = APIRouter()
parsing_service = ParsingService()

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    result = await parsing_service.process(file)
    return result
