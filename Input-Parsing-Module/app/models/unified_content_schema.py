from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class Chunk(BaseModel):
    """chunk of content for RAG/LLM processing"""
    id: str
    content: str 
    chunk_index: int
    metadata: Dict[str, Any] ={}  

class Section(BaseModel):
    """section containing multiple chunks"""
    id: str
    heading: Optional[str]
    page: Optional[int]
    chunks: List[Chunk]

class ParsedContent(BaseModel):
    """parsed document with structured chunks """
    source_type: str
    title: Optional[str]
    sections: List[Section]
    total_chunks: int =0
