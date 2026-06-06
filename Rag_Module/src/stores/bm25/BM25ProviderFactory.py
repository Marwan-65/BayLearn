import os
from .providers.InMemoryBM25 import InMemoryBM25
from .BM25Enums import BM25BackendEnum
from controllers.base import BaseController

class BM25ProviderFactory:
    def __init__(self, config):
        self.config = config
        self.base_controller = BaseController()
    def create(self, provider: str):
        if provider == BM25BackendEnum.IN_MEMORY.value:
            index_dir = os.path.join(
                self.base_controller.base_dir_path,
                self.config.BM25_INDEX_DIR,)
            os.makedirs(index_dir, exist_ok=True)
            return InMemoryBM25(
                index_dir=index_dir,
                k1=self.config.BM25_K1,
                b=self.config.BM25_B,)
        return None
