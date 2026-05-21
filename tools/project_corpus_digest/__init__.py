from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REQUIRED_BASE = [
    "local_source_registry.json",
    "local_file_inventory.json",
    "archive_inventory.json",
    "generation_manifest.json",
]


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def md_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    head = "| " + " | ".join(columns) + " |\n|" + "|".join(["---"] * len(columns)) + "|"
    body = ["| " + " | ".join(str(r.get(c, "")) for c in columns) + " |" for r in rows]
    return "\n".join([head, *body])
