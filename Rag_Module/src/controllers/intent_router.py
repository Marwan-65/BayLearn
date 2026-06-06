import json
import logging
import re
from RAG_module_models.llm_calls import _intent_classify_call
logger = logging.getLogger(__name__)

class IntentRouter:
    INTENTS = [
        "rag_only",
        "equation_from_context",
    ]
    def __init__(self, generation_client):
        self.generation_client = generation_client
    def classify(self, question: str) -> dict:
        fallback = {
            "intent": "rag_only",
            "confidence": 0.0,
            "extracted_params": {},}
        sanitized = self._sanitize_input(question)
        if not sanitized:
            return fallback
        try:
            response = _intent_classify_call(self.generation_client, sanitized)
            if not response:
                logger.warning("Intent classification returned empty response")
                return fallback
            result = json.loads(response)
            intent = result.get("intent", "rag_only")
            if intent not in self.INTENTS:
                logger.warning(
                    f"Unknown intent '{intent}', falling back to rag_only")
                intent = "rag_only"
            extracted_params = result.get("extracted_params", {})
            if not isinstance(extracted_params, dict):
                extracted_params = {}
            return {
                "intent": intent,
                "confidence": min(1.0, max(0.0, float(result.get("confidence", 0.0)))),
                "extracted_params": extracted_params,}
        except json.JSONDecodeError as e:
            logger.warning(f"Intent classification JSON parse failed: {e}")
            return fallback
        except Exception as e:
            logger.warning(f"Intent classification failed: {e}")
            return fallback
    @staticmethod
    def _sanitize_input(text: str, max_length: int = 5000) -> str:
        if not text:
            return ""
        #here remove null bytes
        text = text.replace("\x00", "")
        #here remove control characters except \n \t \r
        text = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        return text[:max_length].strip()
