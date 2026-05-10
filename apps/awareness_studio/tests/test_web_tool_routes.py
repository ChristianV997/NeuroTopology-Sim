"""
Tests for new tool-aware web endpoints — all offline (mocked).
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


# ── /health — tools_enabled field ────────────────────────────────────────────

def test_health_has_tools_enabled():
    resp = client.get("/health")
    assert "tools_enabled" in resp.json()


def test_health_tools_enabled_default_false():
    resp = client.get("/health")
    assert resp.json()["tools_enabled"] is False


# ── /tools/list ───────────────────────────────────────────────────────────────

def test_tools_list_returns_200():
    resp = client.get("/tools/list")
    assert resp.status_code == 200


def test_tools_list_has_expected_keys():
    resp = client.get("/tools/list")
    data = resp.json()
    assert "enabled" in data
    assert "tools" in data
    assert isinstance(data["tools"], list)


# ── /chat — tool_calls field ──────────────────────────────────────────────────

def _mock_llm(text="answer"):
    mock = MagicMock()
    mock.complete.return_value = text
    mock.complete_stream.return_value = iter([text])
    return mock


def test_chat_response_has_tool_calls_field():
    with patch("awareness_studio.web.app.get_llm_client", return_value=_mock_llm()):
        resp = client.post("/chat", json={"question": "What is vedana?", "mode": "EXPLAIN"})
    assert resp.status_code == 200
    assert "tool_calls" in resp.json()


def test_chat_no_tools_flag_produces_empty_tool_calls():
    with patch("awareness_studio.web.app.get_llm_client", return_value=_mock_llm()):
        resp = client.post("/chat", json={
            "question": "What is vedana?", "mode": "EXPLAIN", "use_tools": False
        })
    assert resp.json()["tool_calls"] == []


def test_chat_tools_flag_with_non_trigger_question_no_calls():
    with patch("awareness_studio.web.app.get_llm_client", return_value=_mock_llm()):
        resp = client.post("/chat", json={
            "question": "What is tanha?", "mode": "TEACH", "use_tools": True
        })
    # "What is tanha?" has no trigger keywords → no tool calls
    assert resp.json()["tool_calls"] == []


# ── /literature/search ────────────────────────────────────────────────────────

_FAKE_ESEARCH = b'{"esearchresult": {"idlist": ["99999999"]}}'
_FAKE_ESUMMARY = b'''{
  "result": {
    "99999999": {
      "title": "Consciousness and PCI",
      "authors": [{"name": "Tononi G"}],
      "fulljournalname": "Science",
      "pubdate": "2024 Jan",
      "articleids": [{"idtype": "doi", "value": "10.1000/xyz"}]
    }
  }
}'''


def _fake_urlopen_pub(url, timeout=10):
    mock = MagicMock()
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    if "esearch" in str(url):
        mock.read.return_value = _FAKE_ESEARCH
    else:
        mock.read.return_value = _FAKE_ESUMMARY
    return mock


def test_literature_search_pubmed_returns_200():
    with patch("urllib.request.urlopen", side_effect=_fake_urlopen_pub):
        resp = client.post("/literature/search", json={
            "query": "consciousness PCI", "source": "pubmed", "max_results": 3
        })
    assert resp.status_code == 200


def test_literature_search_pubmed_has_items():
    with patch("urllib.request.urlopen", side_effect=_fake_urlopen_pub):
        resp = client.post("/literature/search", json={
            "query": "consciousness PCI", "source": "pubmed", "max_results": 3
        })
    data = resp.json()
    assert "items" in data
    assert len(data["items"]) >= 1


def test_literature_search_as_card_includes_draft():
    with patch("urllib.request.urlopen", side_effect=_fake_urlopen_pub):
        resp = client.post("/literature/search", json={
            "query": "vedana", "source": "pubmed", "max_results": 1, "as_card": True
        })
    assert resp.status_code == 200
    items = resp.json()["items"]
    if items:
        assert "card_draft" in items[0]


def test_literature_search_invalid_source_returns_422():
    resp = client.post("/literature/search", json={
        "query": "test", "source": "invalid_source"
    })
    assert resp.status_code == 422


def test_literature_search_empty_query_returns_422():
    resp = client.post("/literature/search", json={"query": "", "source": "pubmed"})
    assert resp.status_code == 422


def test_literature_search_tool_record_in_response():
    with patch("urllib.request.urlopen", side_effect=_fake_urlopen_pub):
        resp = client.post("/literature/search", json={
            "query": "consciousness", "source": "pubmed"
        })
    data = resp.json()
    assert "tool_record" in data
    assert data["tool_record"]["tool_name"] == "pubmed_search"


# ── /linear/search ────────────────────────────────────────────────────────────

def test_linear_search_no_key_returns_503():
    import awareness_studio.config as cfg
    orig = cfg.LINEAR_API_KEY
    cfg.LINEAR_API_KEY = ""
    try:
        resp = client.get("/linear/search?query=awareness")
        assert resp.status_code == 503
    finally:
        cfg.LINEAR_API_KEY = orig


_FAKE_LINEAR = b'''{
  "data": {"issues": {"nodes": [
    {"id": "x1", "identifier": "AW-1", "title": "Phase 3",
     "state": {"name": "Done"}, "priority": 1,
     "assignee": {"name": "C"}, "url": "https://linear.app/x",
     "updatedAt": "2026-05-01T00:00:00Z"}
  ]}}
}'''


def _fake_urlopen_linear(req, timeout=10):
    mock = MagicMock()
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    mock.read.return_value = _FAKE_LINEAR
    return mock


def test_linear_search_with_key_returns_issues():
    import awareness_studio.config as cfg
    orig = cfg.LINEAR_API_KEY
    cfg.LINEAR_API_KEY = "lin_api_test"
    try:
        with patch("urllib.request.urlopen", side_effect=_fake_urlopen_linear):
            resp = client.get("/linear/search?query=phase+3")
        assert resp.status_code == 200
        data = resp.json()
        assert "issues" in data
        assert len(data["issues"]) == 1
    finally:
        cfg.LINEAR_API_KEY = orig
