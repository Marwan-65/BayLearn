import os
from .base import BaseController
class ProjectController(BaseController):
    def __init__ (self):
        super().__init__()
    def make_project_dir(self,project_id:str):
        project_dir_path = os.path.join(self.project_dir_path,project_id)
        if not os.path.exists(project_dir_path):
            os.makedirs(project_dir_path)
        return project_dir_path
            
    
        