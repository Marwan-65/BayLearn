from groq import Groq
from sentence_transformers import SentenceTransformer
from ..LLMInterface import LLMInterface
import logging


class GroqProvider(LLMInterface):
    def __init__(self,api_key: str,default_input_max_characters: int = 10000,
    default_generation_max_output_tokens: int = 1024,
    default_generation_temperature: float = 0.1):

        self.api_key = api_key
        self.default_input_max_characters = default_input_max_characters
        self.default_generation_max_output_tokens = default_generation_max_output_tokens
        self.default_generation_temperature = default_generation_temperature

        self.generation_model_id = None
        self.embedding_model_id = None
        self.embedding_size = None

        self.groq_client = None       
        self.embedding_model = None   

        self.logger = logging.getLogger(__name__)


    def set_generation_model(self, model_id: str):
        self.generation_model_id = model_id
        self.groq_client = Groq(api_key=self.api_key)  # Groq = the installed library class
        self.logger.info(f"Groq client initialized with model: {model_id}")

    def generate_text(self, prompt: str, chat_history: list = [],
                    max_output_tokens: int = None, temperature: float = None,
        response_format: dict = None):

        if not self.groq_client:
            self.logger.error("Groq client not initialized.")
            return None

        max_output_tokens = max_output_tokens or self.default_generation_max_output_tokens
        temperature = temperature or self.default_generation_temperature

        messages = chat_history + [
            {"role": "user", "content": prompt}
        ]

        kwargs = dict(
            model=self.generation_model_id,
            messages=messages,
            max_tokens=max_output_tokens,
            temperature=temperature,
        )
        if response_format is not None:
            kwargs["response_format"] = response_format

        try:
            response = self.groq_client.chat.completions.create(**kwargs)
            return response.choices[0].message.content

        except Exception as e:
            self.logger.error(f"Groq generation failed: {e}")
            return None
    def set_embedding_model(self, model_id: str, embedding_size: int):
        self.embedding_model_id = model_id
        self.embedding_size = embedding_size
        self.embedding_model = SentenceTransformer(model_id)
        self.logger.info(f"Embedding model loaded locally: {model_id}")

    def embed_text(self, text: str, document_type: str):
        if not self.embedding_model:
            self.logger.error("Embedding model not initialized.")
            return None
        return self.embedding_model.encode(text).tolist()

    def embed_texts_batch(self, texts: list, document_type: str) -> list:
        if not self.embedding_model:
            self.logger.error("Embedding model not initialized.")
            return []
        return self.embedding_model.encode(texts).tolist()

    def process_text(self, text: str):
        return text[:self.default_input_max_characters].strip()

    def construct_prompt(self, prompt: str, role: str):
        return {"role": role, "content": prompt}