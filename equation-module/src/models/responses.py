from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OperationResponse:
    """Operation output from ai"""
    operation: str
    text: str
    result: Any = None
