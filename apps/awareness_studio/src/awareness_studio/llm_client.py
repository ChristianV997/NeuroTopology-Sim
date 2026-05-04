"""
LLM client abstraction.

Supported providers (LLM_PROVIDER env var):
  anthropic (default) — uses anthropic SDK
  openai              — uses OpenAI-compatible REST via stdlib urllib (no SDK needed)

Unified call signature:
  client.generate(system, messages, temperature, max_tokens) -> str
  client.complete(system, user)                              -> str   (convenience)
  client.complete_stream(system, user)                       -> Iterator[str]
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Iterator

from awareness_studio import config


class BaseLLMClient(ABC):
    """Abstract base for all LLM clients."""

    @abstractmethod
    def generate(
        self,
        system: str,
        messages: list[dict],
        temperature: float = config.LLM_TEMPERATURE,
        max_tokens: int = config.LLM_MAX_TOKENS,
    ) -> str: ...

    def complete(self, system: str, user: str) -> str:
        """Convenience wrapper: single user turn."""
        return self.generate(
            system,
            [{"role": "user", "content": user}],
            temperature=config.LLM_TEMPERATURE,
            max_tokens=config.LLM_MAX_TOKENS,
        )

    def complete_stream(self, system: str, user: str) -> Iterator[str]:
        """Stream response tokens.  Default fallback: yield full text at once."""
        yield self.complete(system, user)


# ── Anthropic ────────────────────────────────────────────────────────────────

class AnthropicClient(BaseLLMClient):
    def __init__(
        self,
        model: str = config.ANTHROPIC_MODEL,
        api_key: str = config.ANTHROPIC_API_KEY,
    ) -> None:
        try:
            import anthropic as _a
        except ImportError as exc:
            raise ImportError("pip install anthropic") from exc
        self._sdk = _a
        self._client = _a.Anthropic(api_key=api_key)
        self.model = model

    def generate(
        self,
        system: str,
        messages: list[dict],
        temperature: float = config.LLM_TEMPERATURE,
        max_tokens: int = config.LLM_MAX_TOKENS,
    ) -> str:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=messages,
        )
        return resp.content[0].text

    def complete_stream(self, system: str, user: str) -> Iterator[str]:
        with self._client.messages.stream(
            model=self.model,
            max_tokens=config.LLM_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            yield from stream.text_stream


# ── OpenAI-compatible (stdlib urllib, no SDK) ────────────────────────────────

class OpenAIClient(BaseLLMClient):
    def __init__(
        self,
        model: str = config.OPENAI_MODEL,
        api_key: str = config.OPENAI_API_KEY,
        base_url: str = config.OPENAI_BASE_URL,
    ) -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set.")
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def _post(self, endpoint: str, payload: dict) -> dict:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{self.base_url}/{endpoint}",
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            raise RuntimeError(f"OpenAI API {exc.code}: {body}") from exc

    def generate(
        self,
        system: str,
        messages: list[dict],
        temperature: float = config.LLM_TEMPERATURE,
        max_tokens: int = config.LLM_MAX_TOKENS,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}] + messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        result = self._post("chat/completions", payload)
        return result["choices"][0]["message"]["content"]

    def complete_stream(self, system: str, user: str) -> Iterator[str]:
        # OpenAI SSE streaming via urllib: parse text/event-stream line by line
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": config.LLM_MAX_TOKENS,
            "stream": True,
        }
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8").rstrip("\n")
                    if not line.startswith("data:"):
                        continue
                    chunk = line[5:].strip()
                    if chunk == "[DONE]":
                        break
                    try:
                        obj = json.loads(chunk)
                        delta = obj["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except (json.JSONDecodeError, KeyError):
                        continue
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            raise RuntimeError(f"OpenAI stream {exc.code}: {body}") from exc


# ── Factory ──────────────────────────────────────────────────────────────────

def get_llm_client() -> BaseLLMClient:
    provider = config.LLM_PROVIDER
    if provider == "anthropic":
        return AnthropicClient()
    if provider == "openai":
        return OpenAIClient()
    raise ValueError(
        f"Unknown LLM_PROVIDER: {provider!r}. "
        "Set LLM_PROVIDER=anthropic or LLM_PROVIDER=openai."
    )
