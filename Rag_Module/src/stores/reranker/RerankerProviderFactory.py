from .providers.CrossEncoderReranker import CrossEncoderReranker
from .RerankerEnums import RerankerBackendEnum


class RerankerProviderFactory:

    def __init__(self, config):
        self.config = config

    def create(self, provider: str):
        if provider == RerankerBackendEnum.CROSS_ENCODER.value:
            return CrossEncoderReranker(
                model_name=self.config.RERANKER_MODEL_ID
            )
        return None
