from .base import BaseController
from fastapi import UploadFile
from models import Response_Signal
class DataController(BaseController):
    def __init__(self):
        super().__init__()
        self.size_scale = 1048576  # 1 MB in bytes
    def validate_file(self,file:UploadFile):
        file_extension = file.filename.split(".")[1].lower()
        print(f"Validating file: {file_extension})")

        # Implement file validation logic here
        if (self.app_settings.FILE_MAX_SIZE * self.size_scale) <= file.size:
            return False, Response_Signal.FILE_SIZE_ERROR.value
        if file_extension not in self.app_settings.FILE_ALLOWED_EXTENSIONS:
            return False, Response_Signal.FILE_EXTENSION_ERROR.value
        return True, Response_Signal.FILE_VALIDATION_SUCCESS.value
    
        
        