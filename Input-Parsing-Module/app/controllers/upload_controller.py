from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.parsing_service import ParsingService


router = APIRouter()
parsing_service = ParsingService()

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        result = await parsing_service.process(file)
        return result
    except ValueError as e:
        # Validation/parsing errors should be client-facing (400), not 500.
        raise HTTPException(status_code=400, detail=str(e))
