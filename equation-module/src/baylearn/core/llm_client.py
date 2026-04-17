"""LLM client for mathematical translation via AI."""

import json
import os
from typing import Dict, Any

from groq import Groq
from dotenv import load_dotenv

from .config import SYSTEM_PROMPT, MODEL_NAME, MODEL_TEMPERATURE

# Load environment variables
load_dotenv()


def get_groq_client() -> Groq:
    """Initialize and return Groq client with API key from environment."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not found in environment variables. "
            "Please check your .env file."
        )
    return Groq(api_key=api_key)


def translate_math_input(user_input: str) -> Dict[str, Any]:
    """
    Translate natural language math input into structured SymPy-compatible format.
    
    Args:
        user_input: User's mathematical query or instruction
        
    Returns:
        Dictionary containing operation, equations, target_variables, etc.
        
    Raises:
        ValueError: If API returns invalid JSON
        RuntimeError: If API call fails
    """
    client = get_groq_client()
    
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_input},
            ],
            response_format={"type": "json_object"},
            temperature=MODEL_TEMPERATURE,
        )
        
        content = response.choices[0].message.content
        if content is None:
            raise RuntimeError("API returned no content")
        
        ai_data = json.loads(content)
        return ai_data
        
    except json.JSONDecodeError as e:
        raise ValueError(f"API returned invalid JSON: {e}")
    except Exception as e:
        raise RuntimeError(f"LLM API call failed: {e}")
