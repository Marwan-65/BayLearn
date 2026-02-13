import os
from .base import BaseController
from fastapi import UploadFile
from models import Response_Signal
import re 
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

    def clean_filename(self,filename:str):
        cleaned_name=re.sub(r'[^\w.]','',filename)
        cleaned_name=cleaned_name.replace(' ','')
        return cleaned_name
    
    def generate_random_filename(self,filename:str,project_id:str):
        cleaned_filename = self.clean_filename(filename)
        random_string = self.generate_random_string(12)
        project_dir_path = self.project_dir_path
        project_dir_path = os.path.join(project_dir_path, f"{project_id}_{random_string}_{cleaned_filename}")
        while os.path.exists(project_dir_path):
            random_string = self.generate_random_string(12)
            project_dir_path = os.path.join(project_dir_path, f"{project_id}_{random_string}_{cleaned_filename}")
        return project_dir_path
    
        
        