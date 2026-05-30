from dataclasses import dataclass
from typing import Dict

@dataclass
class Chunk:
    chunk_id: int
    text: str
    metadata: Dict