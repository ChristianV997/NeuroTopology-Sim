from __future__ import annotations
import json
from pathlib import Path
from typing import Any

DATASET_ID = "DS005620"
DEFAULT_OUT = Path("outputs/btc_icft/ds005620_post_execution_controls")
FORBIDDEN_PHRASES = [
    "proves consciousness","validates consciousness","validates toe","final theory",
    "consciousness solved","q proves","qabs proves","fdress proves","soul","afterlife",
    "enlightenment detector","diagnosis","treatment","cure","clinical efficacy",
]

def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)

def write_json(path: Path, data: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding='utf-8')

def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))
