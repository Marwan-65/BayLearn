"""Typed response models used by operation handlers."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OperationResponse:
    """Operation output payload."""

    operation: str
    text: str
    result: Any = None
