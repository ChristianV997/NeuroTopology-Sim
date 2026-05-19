from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: str, payload: dict[str, Any]) -> None:
    out = Path(path)
    ensure_parent(out)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown(path: str, content: str) -> None:
    out = Path(path)
    ensure_parent(out)
    out.write_text(content.rstrip() + "\n", encoding="utf-8")
