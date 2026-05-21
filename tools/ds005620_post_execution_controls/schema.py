from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Any

@dataclass
class StatusRow:
    row_id: str
    name: str
    purpose: str
    safe_status: str = "planned_only"
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
