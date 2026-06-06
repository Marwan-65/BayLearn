from __future__ import annotations

import os

from question_generation_model.llm.groq_client import QuestionGenLLMClient
try:
    from question_generation_model.llm.gemini_client import GeminiQuestionGenClient
except ImportError:
    GeminiQuestionGenClient = None


def make_llm_client():
    provider = (os.environ.get("LLM_PROVIDER", "groq") or "groq").lower()
    if provider == "gemini":
        if GeminiQuestionGenClient is None:
            raise RuntimeError("google-genai not installed")
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY not set")
        model = os.environ.get("GEMINI_MODEL_ID", "gemini-2.5-flash-lite")
        return GeminiQuestionGenClient(api_key=key, model_id=model), 4.0, model
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY not set")
    model = os.environ.get("GROQ_MODEL_ID", "meta-llama/llama-4-scout-17b-16e-instruct")
    return QuestionGenLLMClient(api_key=key, model_id=model), 1.0, model
