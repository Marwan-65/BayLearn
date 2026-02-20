import random
import string
from helpers.config import get_settings,Settings
import os
class BaseController:
    def __init__(self):
        self.app_settings = get_settings()
        self.base_dir_path = os.path.dirname(os.path.dirname(__file__)) # get the current directory path
        self.project_dir_path = os.path.join(self.base_dir_path,"assets/files") # join adapts to the os and creates the path for the project directory
    def generate_random_string(self,length:int=12):
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))
    def get_database_path(self, db_name: str):
        database_path = os.path.join(
            self.database_dir, db_name
        )
        if not os.path.exists(database_path):
            os.makedirs(database_path)
        return database_path
            