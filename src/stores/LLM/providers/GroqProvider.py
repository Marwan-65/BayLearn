from groq import Groq
from sentence_transformers import SentenceTransformer
from ..LLMInterface import LLMInterface
import logging
import os


class GroqProvider(LLMInterface):
    """
    GroqProvider uses Groq's free cloud API for generation (extremely fast)
    and keeps SentenceTransformer for embeddings locally (embeddings don't
    need the cloud — they're fast enough on CPU already).

    WHY separate embedding from generation here?
    Embedding a short text (384 dimensions) takes ~5ms on CPU.
    Generating 200 tokens takes 3 minutes on your CPU but 0.3s on Groq.
    So we only send generation to the cloud, embeddings stay local.
    """

    def __init__(self,
                 api_key: str,
                 default_input_max_characters: int = 10000,
                 default_generation_max_output_tokens: int = 1024,
                 default_generation_temperature: float = 0.1):

        self.api_key = api_key
        self.default_input_max_characters = default_input_max_characters
        self.default_generation_max_output_tokens = default_generation_max_output_tokens
        self.default_generation_temperature = default_generation_temperature

        self.generation_model_id = None
        self.embedding_model_id = None
        self.embedding_size = None

        self.client = None          # Groq client for generation
        self.embedding_model = None # Local SentenceTransformer for embeddings

        self.logger = logging.getLogger(__name__)

    # ================= GENERATION =================

    def set_generation_model(self, model_id: str):
        """
        Initialize the Groq client.
        model_id examples: "llama3-8b-8192", "llama3-70b-8192", "mixtral-8x7b-32768"
        We use llama3-8b-8192 — free, fast, and much better than Llama 2.
        
        WHY llama3-8b-8192?
        - 8b = 8 billion parameters (same size as your local model)
        - 8192 = context window size in tokens (4x larger than your current 2048)
        - Free tier on Groq
        """
        self.generation_model_id = model_id
        self.client = Groq(api_key=self.api_key)
        self.logger.info(f"Groq client initialized with model: {model_id}")

    def generate_text(self,
                      prompt: str,
                      chat_history: list = [],
                      max_output_tokens: int = None,
                      temperature: float = None):

        if not self.client:
            self.logger.error("Groq client not initialized. Call set_generation_model first.")
            return None

        max_output_tokens = max_output_tokens or self.default_generation_max_output_tokens
        temperature = temperature or self.default_generation_temperature

        # Build messages: system prompt (if any) + user message
        messages = chat_history + [
            {"role": "user", "content": prompt}
        ]

        try:
            response = self.client.chat.completions.create(
                model=self.generation_model_id,
                messages=messages,
                max_tokens=max_output_tokens,
                temperature=temperature
            )
            return response.choices[0].message.content

        except Exception as e:
            self.logger.error(f"Groq generation failed: {e}")
            return None

    # ================= EMBEDDINGS =================

    def set_embedding_model(self, model_id: str, embedding_size: int):
        """
        Embeddings run locally even in Groq mode.
        WHY? Groq doesn't offer embedding models, only generation.
        Also, embeddings are already fast on CPU (~5ms per text).
        So there's no benefit to sending them to the cloud.
        """
        self.embedding_model_id = model_id
        self.embedding_size = embedding_size
        self.embedding_model = SentenceTransformer(model_id)
        self.logger.info(f"Embedding model loaded locally: {model_id}")

    def embed_text(self, text: str, document_type: str):
        if not self.embedding_model:
            self.logger.error("Embedding model not initialized.")
            return None
        return self.embedding_model.encode(text).tolist()

    # ================= HELPERS =================

    def process_text(self, text: str):
        # Much higher limit than LocalProvider since we're not constrained by RAM
        return text[:self.default_input_max_characters].strip()

    def construct_prompt(self, prompt: str, role: str):
        return {
            "role": role,
            "content": prompt
        }