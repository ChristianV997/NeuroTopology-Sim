"""
Tests for P2B UI routes and updated chat response schema.
All offline — mocked LLM client.
"""
import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("EMBEDDING_PROVIDER", "local_stub")
os.environ.setdefault("EMBEDDING_DIM", "64")
os.environ.setdefault("INDEX_BACKEND", "bm25")
os.environ.setdefault("TOOLS_ENABLED", "false")

from fastapi.testclient import TestClient
from awareness_studio.web.app import app

client = TestClient(app)


def _mock_llm(text="[Direct teaching] Vedana is sensation tone.\n\n## Sources used\n- chunk `c1` (book_system)"):
    m = MagicMock()
    m.complete.return_value = text
    m.complete_stream.return_value = iter([text])
    return m


# ── GET / (Control Panel UI) ──────────────────────────────────────────────────

def test_root_returns_200():
    resp = client.get("/")
    assert resp.status_code == 200


def test_root_is_html():
    resp = client.get("/")
    assert "text/html" in resp.headers["content-type"]


def test_root_contains_ui_marker():
    resp = client.get("/")
    # Either the real HTML or the fallback message must contain "Awareness Studio"
    assert b"Awareness Studio" in resp.content


# ── Static files ──────────────────────────────────────────────────────────────

def test_static_css_served():
    resp = client.get("/static/styles.css")
    assert resp.status_code == 200
    assert "css" in resp.headers["content-type"]


def test_static_js_served():
    resp = client.get("/static/app.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers["content-type"]


# ── /chat — sources_used and request_id fields ────────────────────────────────

def test_chat_response_has_sources_used():
    with patch("awareness_studio.web.app.get_llm_client", return_value=_mock_llm()):
        resp = client.post("/chat", json={"question": "What is vedana?", "mode": "EXPLAIN"})
    assert resp.status_code == 200
    assert "sources_used" in resp.json()


def test_chat_response_has_request_id():
    with patch("awareness_studio.web.app.get_llm_client", return_value=_mock_llm()):
        resp = client.post("/chat", json={"question": "What is vedana?", "mode": "EXPLAIN"})
    data = resp.json()
    assert "request_id" in data
    assert data["request_id"] != ""


def test_chat_respects_client_request_id():
    with patch("awareness_studio.web.app.get_llm_client", return_value=_mock_llm()):
        resp = client.post("/chat", json={
            "question": "What is tanha?", "mode": "TEACH",
            "request_id": "my-custom-id"
        })
    assert resp.json()["request_id"] == "my-custom-id"


def test_chat_sources_used_parsed_from_answer():
    answer = "[Direct teaching] Vedana.\n\n## Sources used\n- chunk `c1` (book_system)\n- chunk `c2` (book_seed_q3)"
    with patch("awareness_studio.web.app.get_llm_client", return_value=_mock_llm(answer)):
        resp = client.post("/chat", json={"question": "What is vedana?", "mode": "EXPLAIN"})
    sources = resp.json()["sources_used"]
    assert "c1" in sources
    assert "c2" in sources


def test_chat_no_sources_section_returns_empty_list():
    with patch("awareness_studio.web.app.get_llm_client", return_value=_mock_llm("Just an answer.")):
        resp = client.post("/chat", json={"question": "What is vedana?", "mode": "EXPLAIN"})
    assert resp.json()["sources_used"] == []


# ── /chat — stream includes meta event ───────────────────────────────────────

def test_chat_stream_contains_meta_event():
    with patch("awareness_studio.web.app.get_llm_client", return_value=_mock_llm()):
        resp = client.post("/chat", json={
            "question": "What is vedana?", "mode": "EXPLAIN", "stream": True
        })
    assert "meta" in resp.text or "sources_used" in resp.text or "[DONE]" in resp.text


# ── /health — tools_enabled ───────────────────────────────────────────────────

def test_health_has_tools_enabled():
    resp = client.get("/health")
    assert "tools_enabled" in resp.json()


# ── Stable schema (Expo-readiness) ────────────────────────────────────────────

def test_chat_schema_all_fields_present():
    """Verify the full stable schema required by mobile/Expo clients."""
    with patch("awareness_studio.web.app.get_llm_client", return_value=_mock_llm()):
        resp = client.post("/chat", json={"question": "What is vedana?", "mode": "EXPLAIN"})
    data = resp.json()
    for field in ("answer", "sources_used", "tool_calls", "mode", "request_id", "retrieved"):
        assert field in data, f"Missing schema field: {field}"


# ── Auth gate on /airtable/sync/runs ─────────────────────────────────────────

def test_sync_runs_no_auth_required_by_default():
    """When AUTH_ENABLED is false (default), no key needed."""
    resp = client.post("/airtable/sync/runs?allow_write=false")
    assert resp.status_code == 200


def test_sync_runs_auth_rejects_missing_key(monkeypatch):
    import awareness_studio.config as cfg
    monkeypatch.setattr(cfg, "AUTH_ENABLED", True)
    monkeypatch.setattr(cfg, "AUTH_API_KEY", "secret-key")
    resp = client.post("/airtable/sync/runs?allow_write=false")
    assert resp.status_code == 401


def test_sync_runs_auth_accepts_correct_key(monkeypatch):
    import awareness_studio.config as cfg
    monkeypatch.setattr(cfg, "AUTH_ENABLED", True)
    monkeypatch.setattr(cfg, "AUTH_API_KEY", "secret-key")
    resp = client.post(
        "/airtable/sync/runs?allow_write=false",
        headers={"X-Awareness-Key": "secret-key"},
    )
    assert resp.status_code == 200


def test_sync_runs_auth_rejects_wrong_key(monkeypatch):
    import awareness_studio.config as cfg
    monkeypatch.setattr(cfg, "AUTH_ENABLED", True)
    monkeypatch.setattr(cfg, "AUTH_API_KEY", "secret-key")
    resp = client.post(
        "/airtable/sync/runs?allow_write=false",
        headers={"X-Awareness-Key": "wrong-key"},
    )
    assert resp.status_code == 401
