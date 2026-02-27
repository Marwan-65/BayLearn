from .providers.LocalProvider import LocalProvider


class LLMProviderFactory:

    def __init__(self, config):
        self.config = config

    def create(self, provider: str):
        if provider == "LOCAL":
            return LocalProvider(
                default_input_max_characters=self.config.INPUT_DEFAULT_MAX_CHARACTERS,
                default_generation_max_output_tokens=self.config.GENERATION_DEFAULT_MAX_TOKENS,
                default_generation_temperature=self.config.GENERATION_DEFAULT_TEMPERATURE
            )

        return None