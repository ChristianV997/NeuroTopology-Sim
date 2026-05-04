import hashlib
import re
from typing import List


def stable_id(source_path: str, heading_path: str, index: int) -> str:
    key = f"{source_path}|{heading_path}|{index}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def simple_tokenize(text: str) -> List[str]:
    tokens = re.split(r"[^\wÀ-ɏ]+", text.lower())
    return [t for t in tokens if len(t) > 1]
