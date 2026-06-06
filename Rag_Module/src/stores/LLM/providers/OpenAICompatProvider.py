import logging
import os
import time
import re
from openai import OpenAI
from sentence_transformers import SentenceTransformer
from ..LLMInterface import LLMInterface


class OpenAICompatProvider(LLMInterface):
    def __init__(self,
                 api_key: str,
                 base_url: str = "https://api.cerebras.ai/v1",
                 default_input_max_characters: int = 10000,
                 default_generation_max_output_tokens: int = 1024,
                 default_generation_temperature: float = 0.1):
        self.api_key = api_key
        self.base_url = base_url
        self.default_input_max_characters = default_input_max_characters
        self.default_generation_max_output_tokens = default_generation_max_output_tokens
        self.default_generation_temperature = default_generation_temperature

        self.generation_model_id = None
        self.embedding_model_id = None
        self.embedding_size = None
        self.client = None
        self.embedding_model = None
        self.logger = logging.getLogger(__name__)
    def set_generation_model(self, model_id: str):
        self.generation_model_id = model_id
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.logger.info(f"OpenAI-compat client ready: {model_id} @ {self.base_url}")

    def generate_text(self, prompt: str, chat_history: list = [],
                      max_output_tokens: int = None, temperature: float = None,
                      response_format: dict = None):
        if not self.client:
            self.logger.error("OpenAI-compat client not initialized.")
            return None
        max_output_tokens = max_output_tokens or self.default_generation_max_output_tokens
        temperature = temperature if temperature is not None else self.default_generation_temperature

        messages = list(chat_history) + [{"role": "user", "content": prompt}]
        kwargs = dict(model=self.generation_model_id, messages=messages,
                      max_tokens=max_output_tokens, temperature=temperature)
        if response_format is not None:
            kwargs["response_format"] = response_format

        max_retries = 6
        MAX_RETRY_DELAY = int(os.environ.get("OC_MAX_RETRY_DELAY", "30"))
        for attempt in range(max_retries + 1):
            try:
                resp = self.client.chat.completions.create(**kwargs)
                return resp.choices[0].message.content
            except Exception as e:
                msg = str(e)
                if ("429" in msg or "rate" in msg.lower()) and attempt < max_retries:
                    m = re.search(r"(\d+(?:\.\d+)?)\s*s", msg)
                    raw_delay = float(m.group(1)) + 1 if m else min(2 ** attempt * 3, MAX_RETRY_DELAY)
                    delay = min(raw_delay, MAX_RETRY_DELAY)
                    self.logger.warning(
                        f"OpenAI-compat 429 (attempt {attempt+1}/{max_retries}); "
                        f"backing off {delay:.0f}s")
                    time.sleep(delay)
                    continue
                self.logger.error(f"OpenAI-compat generation failed: {e}")
                return None

    def set_embedding_model(self, model_id: str, embedding_size: int):
        self.embedding_model_id = model_id
        self.embedding_size = embedding_size
        self.embedding_model = SentenceTransformer(model_id)

    def embed_text(self, text: str, document_type: str):
        if not self.embedding_model:
            self.logger.error("Embedding model not initialized.")
            return None
        return self.embedding_model.encode(text).tolist()

    def embed_texts_batch(self, texts: list, document_type: str) -> list:
        if not self.embedding_model:
            return []
        return self.embedding_model.encode(texts).tolist()

    def process_text(self, text: str):
        return text[:self.default_input_max_characters].strip()

    def construct_prompt(self, prompt: str, role: str):
        return {"role": role, "content": prompt}
