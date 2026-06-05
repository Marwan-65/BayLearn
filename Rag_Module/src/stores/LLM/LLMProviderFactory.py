from .providers.LocalProvider import LocalProvider
from .providers.GroqProvider import GroqProvider
from .providers.GeminiProvider import GeminiProvider
from .providers.OpenAICompatProvider import OpenAICompatProvider
from stores.LLM.LLMEnums import LLMBackendEnum

class LLMProviderFactory:

    def __init__(self, config):
        self.config = config

    def create(self, provider: str):
        if provider == LLMBackendEnum.LOCAL.value:
            return LocalProvider(
                default_input_max_characters=self.config.INPUT_DEFAULT_MAX_CHARACTERS,
                default_generation_max_output_tokens=self.config.GENERATION_DEFAULT_MAX_TOKENS,
                default_generation_temperature=self.config.GENERATION_DEFAULT_TEMPERATURE
            )
        if provider == LLMBackendEnum.GROQ.value:
            return GroqProvider(
                api_key=self.config.GROQ_API_KEY,
                default_generation_max_output_tokens=self.config.GENERATION_DEFAULT_MAX_TOKENS,
                default_generation_temperature=self.config.GENERATION_DEFAULT_TEMPERATURE
            )

        if provider == LLMBackendEnum.GEMINI.value:
            return GeminiProvider(
                api_key=self.config.GEMINI_API_KEY,
                default_generation_max_output_tokens=self.config.GENERATION_DEFAULT_MAX_TOKENS,
                default_generation_temperature=self.config.GENERATION_DEFAULT_TEMPERATURE
            )

        if provider == LLMBackendEnum.OPENAI_COMPAT.value:
            return OpenAICompatProvider(
                api_key=self.config.OPENAI_COMPAT_API_KEY,
                base_url=getattr(self.config, "OPENAI_COMPAT_BASE_URL",
                                 "https://api.cerebras.ai/v1"),
                default_generation_max_output_tokens=self.config.GENERATION_DEFAULT_MAX_TOKENS,
                default_generation_temperature=self.config.GENERATION_DEFAULT_TEMPERATURE
            )
        return None