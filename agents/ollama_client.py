"""Thin client for a local Ollama server.

Every call degrades gracefully: if Ollama is unreachable or errors out,
``generate`` returns ``None`` so callers can fall back to a deterministic
policy (e.g. FIFO queue order) instead of blocking the orchestrator loop.
"""
import time
from typing import Optional

import httpx

OLLAMA_BASE = "http://localhost:11434"
DEFAULT_MODEL = "llama3.1:8b"
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds


def generate(prompt: str, model: str = DEFAULT_MODEL, timeout: int = 120) -> Optional[str]:
    """Call Ollama's /api/generate endpoint with retry and graceful fallback."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = httpx.post(
                f"{OLLAMA_BASE}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json()["response"].strip()
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
            else:
                print(f"[Ollama] Unavailable after {MAX_RETRIES} attempts: {e}")
                return None
        except httpx.HTTPStatusError as e:
            print(f"[Ollama] HTTP error: {e}")
            return None
    return None


def is_available() -> bool:
    try:
        httpx.get(f"{OLLAMA_BASE}/api/tags", timeout=3).raise_for_status()
        return True
    except Exception:
        return False
