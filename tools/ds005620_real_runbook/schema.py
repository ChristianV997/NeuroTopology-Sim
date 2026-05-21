from __future__ import annotations
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class FileCheck:
    category: str
    expected: list[str]
    found: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
