import os

from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:
    from langchain_community.embeddings import HuggingFaceEmbeddings

from RAG_module_models.chatgroqfixed import GroqChatFixed


def build_embeddings():
    emb = HuggingFaceEmbeddings(
        model_name="BAAI/bge-small-en-v1.5",
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )
    return LangchainEmbeddingsWrapper(emb)


def build_openai_compat_judge(api_key, base_url, model):
    llm = ChatOpenAI(
        model=model or "llama-3.3-70b",
        api_key=api_key,
        base_url=base_url or "https://api.cerebras.ai/v1",
        temperature=0,
        max_tokens=2048,
        max_retries=10,
        timeout=120,
    )
    return LangchainLLMWrapper(llm)


def build_gemini_judge(api_key, model):
    llm = ChatGoogleGenerativeAI(
        model=model,
        google_api_key=api_key,
        temperature=0,
        max_output_tokens=2048,
        transport="rest",
    )
    return LangchainLLMWrapper(llm)


def build_groq_judge(api_key):
    llm = GroqChatFixed(
        model="llama-3.1-8b-instant",
        groq_api_key=api_key,
        temperature=0,
        max_tokens=900,
        timeout=120.0,
        max_retries=4,
    )
    return LangchainLLMWrapper(llm)
