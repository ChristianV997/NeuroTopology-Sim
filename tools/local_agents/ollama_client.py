"""
Optional Ollama client using stdlib urllib only (P23).

No third-party dependencies. Degrades gracefully when Ollama is not installed
or not running. All callers should check is_available() before calling chat().
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional


_DEFAULT_BASE_URL = "http://localhost:11434"
_DEFAULT_MODEL = "llama3"
_CONNECT_TIMEOUT_S = 3


class OllamaClient:
    """Minimal Ollama REST client using stdlib urllib."""

    def __init__(
        self,
        base_url: str = _DEFAULT_BASE_URL,
        default_model: str = _DEFAULT_MODEL,
        timeout_s: int = 60,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.timeout_s = timeout_s

    def is_available(self) -> bool:
        """Return True if Ollama server responds to /api/tags."""
        try:
            url = f"{self.base_url}/api/tags"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=_CONNECT_TIMEOUT_S):
                return True
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """Return list of local model names. Returns [] on any error."""
        try:
            url = f"{self.base_url}/api/tags"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=_CONNECT_TIMEOUT_S) as resp:
                data = json.loads(resp.read().decode())
            return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        except Exception:
            return []

    def chat(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        stream: bool = False,
    ) -> dict:
        """
        Send a chat completion request to Ollama.

        Returns dict with keys: model, response, done, error (if any).
        On any error returns {"error": <str>, "response": "", "done": False}.
        """
        m = model or self.default_model
        payload: dict = {
            "model": m,
            "prompt": prompt,
            "stream": stream,
        }
        if system:
            payload["system"] = system

        body = json.dumps(payload).encode("utf-8")
        url = f"{self.base_url}/api/generate"
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            return {
                "model": data.get("model", m),
                "response": data.get("response", ""),
                "done": data.get("done", True),
                "error": "",
            }
        except urllib.error.URLError as exc:
            return {"model": m, "response": "", "done": False, "error": str(exc)}
        except Exception as exc:
            return {"model": m, "response": "", "done": False, "error": str(exc)}
