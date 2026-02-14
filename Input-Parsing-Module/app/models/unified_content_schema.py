from pydantic import BaseModel
from typing import List, Optional

class Section(BaseModel):
    heading: Optional[str]
    content: str
    page: Optional[int]

class ParsedContent(BaseModel):
    source_type: str
    title: Optional[str]
    sections: List[Section]
    keywords: List[str]
    difficulty_level: Optional[str]
    estimated_duration: Optional[int]
