import os
from fastapi import UploadFile

UPLOAD_DIR = "uploads"

async def save_upload_file(upload_file: UploadFile):
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    file_path = os.path.join(UPLOAD_DIR, upload_file.filename)

    with open(file_path, "wb") as buffer:
        buffer.write(await upload_file.read())

    return file_path
