from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class Chunk(BaseModel):
    """Individual chunk of content suitable for RAG/LLM processing"""
    id: str
    content: str  # Clean, prepared text for LLM
    chunk_index: int
    metadata: Dict[str, Any] = {}  # Page number, section heading, position, etc.

class Section(BaseModel):
    """Logical section containing multiple chunks"""
    id: str
    heading: Optional[str]
    page: Optional[int]
    chunks: List[Chunk]

class ParsedContent(BaseModel):
    """Complete parsed document with structured chunks ready for RAG/LLM"""
    source_type: str
    title: Optional[str]
    sections: List[Section]
    keywords: List[str]
    difficulty_level: Optional[str]
    estimated_duration: Optional[int]
    total_chunks: int = 0  # Total number of chunks across all sections
