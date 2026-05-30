import logging
from groq import Groq

logger = logging.getLogger(__name__)

class QuestionGenLLMClient:
    """
    Thin wrapper around the Groq API for text generation.
    Mirrors the pattern in src/stores/LLM/providers/GroqProvider.py
    but only does generation (no embeddings needed here).
    """

    def __init__(self, api_key: str, model_id: str):
        self.model_id = model_id
        self.client = Groq(api_key=api_key)

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 900,
    ) -> str:
        """
        Send a prompt to Groq and return the generated text.
        
        system_prompt: Instructions for how the LLM should behave
        user_prompt: The actual task (e.g., "generate questions from this text")
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content
            return content if content is not None else ""
        except Exception as e:
            logger.error(f"Groq generation failed: {e}")
            raise