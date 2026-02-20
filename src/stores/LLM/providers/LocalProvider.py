from llama_cpp import Llama
from sentence_transformers import SentenceTransformer
from ..LLMInterface import LLMInterface
import logging


class LocalProvider(LLMInterface):

    def __init__(self,
                 model_path: str = None,
                 embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
                 default_input_max_characters: int = 1000,
                 default_generation_max_output_tokens: int = 512,
                 default_generation_temperature: float = 0.1):

        self.model_path = model_path
        self.embedding_model_name = embedding_model_name

        self.default_input_max_characters = default_input_max_characters
        self.default_generation_max_output_tokens = default_generation_max_output_tokens
        self.default_generation_temperature = default_generation_temperature

        self.generation_model_id = None
        self.embedding_model_id = None
        self.embedding_size = None

        self.llm = None
        self.embedding_model = None

        self.logger = logging.getLogger(__name__)

    # ================= GENERATION =================

    def set_generation_model(self, model_id: str):
        self.generation_model_id = model_id

        self.llm = Llama(
            model_path=model_id,
            n_ctx=2048,
            n_threads=6,
            n_gpu_layers=20  # uses Metal on M1
        )

    def generate_text(self, prompt: str,
                      chat_history: list = [],
                      max_output_tokens: int = None,
                      temperature: float = None):

        if not self.llm:
            self.logger.error("Local LLM not initialized")
            return None

        max_output_tokens = max_output_tokens or self.default_generation_max_output_tokens
        temperature = temperature or self.default_generation_temperature

        messages = chat_history + [
            {"role": "user", "content": self.process_text(prompt)}
        ]

        response = self.llm.create_chat_completion(
            messages=messages,
            max_tokens=max_output_tokens,
            temperature=temperature
        )

        return response["choices"][0]["message"]["content"]

    # ================= EMBEDDINGS =================

    def set_embedding_model(self, model_id: str, embedding_size: int):
        self.embedding_model_id = model_id
        self.embedding_size = embedding_size

        self.embedding_model = SentenceTransformer(model_id)

    def embed_text(self, text: str, document_type: str):

        if not self.embedding_model:
            self.logger.error("Embedding model not initialized")
            return None

        return self.embedding_model.encode(text).tolist()

    # ================= HELPERS =================

    def process_text(self, text: str):
        return text[:self.default_input_max_characters].strip()

    def construct_prompt(self, prompt: str, role: str):
        return {
            "role": role,
            "content": self.process_text(prompt)
        }