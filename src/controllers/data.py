from .base import BaseController
from fastapi import UploadFile

class DataController(BaseController):
    
    def __init_(self):
        super().__init__()
        self.size_scale = 1048576  # 1 MB in bytes
        
    def validate_file(self,file:UploadFile):
        # Implement file validation logic here
        if (self.app_settings.FILE_MAX_SIZE * self.size_scale) <= file.size:
            raise ValueError("File size exceeds the maximum limit")
        if file.extension not in self.app_settings.FILE_ALLOWED_EXTENSIONS:
            raise ValueError("File type is not allowed")
        return True
        