import logging
from google import genai
from google.genai import types
from sentence_transformers import SentenceTransformer
from ..LLMInterface import LLMInterface


class GeminiProvider(LLMInterface):
    """
    Uses Google Gemini for generation (free tier: 1M TPM, 1500 RPD)
    and local SentenceTransformer for embeddings — same split as GroqProvider.

    Uses the new google-genai SDK (google-generativeai is deprecated).
    Free API key: https://aistudio.google.com/app/apikey
    Recommended model: gemini-2.0-flash-lite  (fastest, generous free quota)
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
        self.embedding_model = None
        self._client = None

        self.logger = logging.getLogger(__name__)

    # ── Generation ────────────────────────────────────────────────────────

    def set_generation_model(self, model_id: str):
        self.generation_model_id = model_id
        self._client = genai.Client(api_key=self.api_key)
        self.logger.info(f"Gemini generation model set: {model_id}")

    def generate_text(self, prompt: str, chat_history: list = [],
                      max_output_tokens: int = None, temperature: float = None,
                      response_format: dict = None):

        if not self.generation_model_id or not self._client:
            self.logger.error("Gemini generation model not initialized.")
            return None

        max_output_tokens = max_output_tokens or self.default_generation_max_output_tokens
        temperature = temperature if temperature is not None else self.default_generation_temperature

        # Extract system instruction from chat_history (OpenAI-style compat)
        system_parts = [
            m["content"] for m in chat_history
            if m.get("role") == "system"
        ]
        system_instruction = "\n\n".join(system_parts) if system_parts else None

        # Build conversation turns (user/assistant only)
        contents = []
        for m in chat_history:
            role = m.get("role")
            if role == "user":
                contents.append(types.Content(role="user", parts=[types.Part(text=m["content"])]))
            elif role == "assistant":
                contents.append(types.Content(role="model", parts=[types.Part(text=m["content"])]))
        # Add current user prompt
        contents.append(types.Content(role="user", parts=[types.Part(text=prompt)]))

        config_kwargs = {
            "max_output_tokens": max_output_tokens,
            "temperature": temperature,
        }
        if response_format and response_format.get("type") == "json_object":
            config_kwargs["response_mime_type"] = "application/json"

        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction

        generate_config = types.GenerateContentConfig(**config_kwargs)

        try:
            response = self._client.models.generate_content(
                model=self.generation_model_id,
                contents=contents,
                config=generate_config,
            )
            return response.text

        except Exception as e:
            self.logger.error(f"Gemini generation failed: {e}")
            return None

    # ── Embeddings (local SentenceTransformer) ────────────────────────────

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

    # ── Helpers ───────────────────────────────────────────────────────────

    def process_text(self, text: str):
        return text[:self.default_input_max_characters].strip()

    def construct_prompt(self, prompt: str, role: str):
        return {"role": role, "content": prompt}
