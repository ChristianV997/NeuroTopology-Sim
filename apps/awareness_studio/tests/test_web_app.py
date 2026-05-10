"""
Tests for the FastAPI web frontend.

All offline — uses local_stub embedding and mocks the LLM client.
"""
import os

import pytest

os.environ.setdefault("EMBEDDING_PROVIDER", "local_stub")
os.environ.setdefault("EMBEDDING_DIM", "64")
os.environ.setdefault("INDEX_BACKEND", "bm25")

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from awareness_studio.web.app import app

client = TestClient(app)


# ── /health ───────────────────────────────────────────────────────────────────

def test_health_status_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_health_backend_field():
    resp = client.get("/health")
    data = resp.json()
    assert "backend" in data


def test_health_embedding_provider_none_for_bm25():
    resp = client.get("/health")
    data = resp.json()
    if data["backend"] == "bm25":
        assert data["embedding_provider"] is None


# ── /chat — validation ────────────────────────────────────────────────────────

def test_chat_empty_question_rejected():
    resp = client.post("/chat", json={"question": "", "mode": "EXPLAIN"})
    assert resp.status_code == 422


def test_chat_invalid_mode_rejected():
    resp = client.post("/chat", json={"question": "What is vedana?", "mode": "INVALID"})
    assert resp.status_code == 422


def test_chat_k_out_of_range():
    resp = client.post("/chat", json={"question": "vedana", "mode": "EXPLAIN", "k": 0})
    assert resp.status_code == 422


# ── /chat — non-streaming ─────────────────────────────────────────────────────

def _mock_client(response_text: str):
    mock = MagicMock()
    mock.complete.return_value = response_text
    mock.complete_stream.return_value = iter([response_text])
    return mock


def test_chat_non_stream_returns_json():
    with patch("awareness_studio.web.app.get_llm_client", return_value=_mock_client("answer text")):
        resp = client.post("/chat", json={"question": "What is vedana?", "mode": "EXPLAIN"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "answer text"
    assert data["mode"] == "EXPLAIN"
    assert isinstance(data["retrieved"], int)


def test_chat_mode_normalised_to_upper():
    with patch("awareness_studio.web.app.get_llm_client", return_value=_mock_client("ok")):
        resp = client.post("/chat", json={"question": "vedana?", "mode": "explain"})
    assert resp.status_code == 200
    assert resp.json()["mode"] == "EXPLAIN"


def test_chat_all_valid_modes():
    modes = ["TEACH", "EXPLAIN", "ELABORATE", "MATRIX", "CARD", "CANONICAL"]
    for mode in modes:
        with patch("awareness_studio.web.app.get_llm_client", return_value=_mock_client("ok")):
            resp = client.post("/chat", json={"question": "vedana?", "mode": mode})
        assert resp.status_code == 200, f"mode={mode} failed with {resp.status_code}"


def test_chat_retrieved_count_non_negative():
    with patch("awareness_studio.web.app.get_llm_client", return_value=_mock_client("ok")):
        resp = client.post("/chat", json={"question": "liberation", "mode": "EXPLAIN"})
    assert resp.json()["retrieved"] >= 0


# ── /chat — streaming ─────────────────────────────────────────────────────────

def test_chat_stream_returns_event_stream():
    with patch("awareness_studio.web.app.get_llm_client", return_value=_mock_client("tok1")):
        resp = client.post(
            "/chat",
            json={"question": "What is tanha?", "mode": "TEACH", "stream": True},
        )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]


def test_chat_stream_contains_done_sentinel():
    with patch("awareness_studio.web.app.get_llm_client", return_value=_mock_client("hello")):
        resp = client.post(
            "/chat",
            json={"question": "vedana?", "mode": "EXPLAIN", "stream": True},
        )
    assert "[DONE]" in resp.text


def test_chat_stream_contains_data_lines():
    with patch("awareness_studio.web.app.get_llm_client", return_value=_mock_client("token")):
        resp = client.post(
            "/chat",
            json={"question": "samsara?", "mode": "EXPLAIN", "stream": True},
        )
    assert "data:" in resp.text
