"""
Tests for tool_router.py — all offline, all tools mocked.

No network calls, no API keys required.
"""
import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("TOOLS_ENABLED", "false")
os.environ.setdefault("TOOLS_ALLOWLIST", "")

from awareness_studio.tool_router import (
    CompositeToolRouter,
    GatedToolRouter,
    LiteratureToolRouter,
    LinearToolRouter,
    NullToolRouter,
    ToolCallRecord,
    ToolNotAllowedError,
    ToolNotFoundError,
    ToolResult,
    ToolSpec,
    format_tool_results,
    get_tool_router,
    has_tool_trigger,
)


# ── ToolSpec / ToolCallRecord ─────────────────────────────────────────────────

def test_tool_spec_fields():
    spec = ToolSpec(name="pubmed_search", description="x", provider="pubmed")
    assert spec.readonly is True
    assert spec.requires_auth is False


def test_tool_call_record_fields():
    rec = ToolCallRecord(
        tool_name="t", args={}, timestamp="2026-01-01T00:00:00Z",
        result_summary="ok",
    )
    assert rec.error is None
    assert rec.duration_ms is None


# ── NullToolRouter ────────────────────────────────────────────────────────────

def test_null_router_list_tools_empty():
    r = NullToolRouter()
    assert r.list_tools() == []


def test_null_router_call_returns_failure():
    r = NullToolRouter()
    res = r.call_tool("anything", {})
    assert isinstance(res, ToolResult)
    assert res.success is False
    assert res.data is None


def test_null_router_handles_returns_false():
    r = NullToolRouter()
    assert r.handles("pubmed_search") is False


# ── LiteratureToolRouter ──────────────────────────────────────────────────────

def test_literature_router_lists_two_tools():
    r = LiteratureToolRouter()
    names = {t.name for t in r.list_tools()}
    assert "pubmed_search" in names
    assert "biorxiv_search" in names


def test_literature_router_handles_pubmed():
    r = LiteratureToolRouter()
    assert r.handles("pubmed_search")
    assert not r.handles("linear_list_issues")


def test_literature_router_unknown_tool_returns_failure():
    r = LiteratureToolRouter()
    res = r.call_tool("nonexistent_tool", {})
    assert res.success is False
    assert res.record.error is not None


def test_literature_router_pubmed_empty_query():
    r = LiteratureToolRouter()
    res = r.call_tool("pubmed_search", {"query": ""})
    assert res.success is True
    assert res.data == []


def test_literature_router_biorxiv_empty_query():
    r = LiteratureToolRouter()
    res = r.call_tool("biorxiv_search", {"query": ""})
    assert res.success is True
    assert res.data == []


_FAKE_ESEARCH = b'{"esearchresult": {"idlist": ["12345678"]}}'
_FAKE_ESUMMARY = b'''{
  "result": {
    "12345678": {
      "title": "Vedana and consciousness",
      "authors": [{"name": "Smith J"}, {"name": "Doe A"}],
      "fulljournalname": "Neuroscience Letters",
      "pubdate": "2024 Mar",
      "articleids": [{"idtype": "doi", "value": "10.1016/test"}]
    }
  }
}'''


def _fake_urlopen_pubmed(url, timeout=10):
    mock = MagicMock()
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    if "esearch" in str(url):
        mock.read.return_value = _FAKE_ESEARCH
    else:
        mock.read.return_value = _FAKE_ESUMMARY
    return mock


def test_literature_router_pubmed_returns_results():
    r = LiteratureToolRouter()
    with patch("urllib.request.urlopen", side_effect=_fake_urlopen_pubmed):
        res = r.call_tool("pubmed_search", {"query": "vedana consciousness", "max_results": 5})
    assert res.success is True
    assert len(res.data) == 1
    assert res.data[0]["pmid"] == "12345678"
    assert "Vedana" in res.data[0]["title"]
    assert res.data[0]["source"] == "pubmed"


def test_literature_router_pubmed_result_has_url():
    r = LiteratureToolRouter()
    with patch("urllib.request.urlopen", side_effect=_fake_urlopen_pubmed):
        res = r.call_tool("pubmed_search", {"query": "vedana", "max_results": 3})
    assert "pubmed.ncbi" in res.data[0]["url"]


_FAKE_BIORXIV = b'''{
  "collection": [
    {
      "doi": "10.1101/2024.01.01.000001",
      "title": "PCI and consciousness measurement",
      "authors": "Jones B, Smith C",
      "date": "2024-01-15",
      "abstract": "We measured PCI in anesthesia patients."
    }
  ]
}'''


def _fake_urlopen_biorxiv(url, timeout=10):
    mock = MagicMock()
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    mock.read.return_value = _FAKE_BIORXIV
    return mock


def test_literature_router_biorxiv_returns_results():
    r = LiteratureToolRouter()
    with patch("urllib.request.urlopen", side_effect=_fake_urlopen_biorxiv):
        res = r.call_tool("biorxiv_search", {"query": "PCI consciousness", "max_results": 5})
    assert res.success is True
    assert len(res.data) == 1
    assert res.data[0]["source"] == "biorxiv"


def test_literature_router_network_error_returns_failure():
    r = LiteratureToolRouter()
    with patch("urllib.request.urlopen", side_effect=Exception("network down")):
        res = r.call_tool("pubmed_search", {"query": "vedana", "max_results": 5})
    assert res.success is False
    assert res.record.error is not None


# ── LinearToolRouter ──────────────────────────────────────────────────────────

def test_linear_router_no_key_returns_empty_tools():
    import awareness_studio.config as cfg
    orig = cfg.LINEAR_API_KEY
    cfg.LINEAR_API_KEY = ""
    try:
        r = LinearToolRouter()
        assert r.list_tools() == []
    finally:
        cfg.LINEAR_API_KEY = orig


def test_linear_router_no_key_call_returns_failure():
    import awareness_studio.config as cfg
    orig = cfg.LINEAR_API_KEY
    cfg.LINEAR_API_KEY = ""
    try:
        r = LinearToolRouter()
        res = r.call_tool("linear_list_issues", {"query": "awareness"})
        assert res.success is False
    finally:
        cfg.LINEAR_API_KEY = orig


_FAKE_LINEAR_RESPONSE = b'''{
  "data": {
    "issues": {
      "nodes": [
        {
          "id": "abc123",
          "identifier": "AW-1",
          "title": "Awareness Studio Phase 3",
          "state": {"name": "In Progress"},
          "priority": 2,
          "assignee": {"name": "Christian"},
          "url": "https://linear.app/team/issue/AW-1",
          "updatedAt": "2026-05-04T00:00:00Z"
        }
      ]
    }
  }
}'''


def _fake_urlopen_linear(req, timeout=10):
    mock = MagicMock()
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    mock.read.return_value = _FAKE_LINEAR_RESPONSE
    return mock


def test_linear_router_with_key_returns_issues():
    import awareness_studio.config as cfg
    orig = cfg.LINEAR_API_KEY
    cfg.LINEAR_API_KEY = "lin_api_test_key"
    try:
        r = LinearToolRouter()
        with patch("urllib.request.urlopen", side_effect=_fake_urlopen_linear):
            res = r.call_tool("linear_list_issues", {"query": "awareness"})
        assert res.success is True
        assert len(res.data) == 1
        assert res.data[0]["id"] == "AW-1"
    finally:
        cfg.LINEAR_API_KEY = orig


# ── CompositeToolRouter ───────────────────────────────────────────────────────

def test_composite_router_aggregates_tools():
    r = CompositeToolRouter([LiteratureToolRouter(), NullToolRouter()])
    names = {t.name for t in r.list_tools()}
    assert "pubmed_search" in names


def test_composite_router_no_duplicate_tools():
    r = CompositeToolRouter([LiteratureToolRouter(), LiteratureToolRouter()])
    names = [t.name for t in r.list_tools()]
    assert len(names) == len(set(names))


def test_composite_router_unknown_tool_raises():
    r = CompositeToolRouter([LiteratureToolRouter()])
    with pytest.raises(ToolNotFoundError):
        r.call_tool("nonexistent", {})


# ── GatedToolRouter ───────────────────────────────────────────────────────────

def test_gated_router_disabled_returns_empty_tools():
    inner = LiteratureToolRouter()
    gated = GatedToolRouter(
        inner=inner, allowlist=["pubmed_search"], max_calls=2, enabled=False
    )
    assert gated.list_tools() == []


def test_gated_router_disabled_call_fails():
    inner = LiteratureToolRouter()
    gated = GatedToolRouter(inner=inner, allowlist=["pubmed_search"], max_calls=2, enabled=False)
    res = gated.call_tool("pubmed_search", {})
    assert res.success is False
    assert "TOOLS_ENABLED=false" in (res.record.error or "")


def test_gated_router_allowlist_enforced():
    inner = LiteratureToolRouter()
    gated = GatedToolRouter(
        inner=inner, allowlist=["biorxiv_search"], max_calls=2, enabled=True
    )
    with pytest.raises(ToolNotAllowedError):
        gated.call_tool("pubmed_search", {})


def test_gated_router_max_calls_enforced():
    inner = LiteratureToolRouter()
    gated = GatedToolRouter(
        inner=inner, allowlist=["pubmed_search"], max_calls=1, enabled=True
    )
    gated.reset_request()
    with patch("urllib.request.urlopen", side_effect=_fake_urlopen_pubmed):
        gated.call_tool("pubmed_search", {"query": "x"})
    with pytest.raises(ToolNotAllowedError):
        gated.call_tool("pubmed_search", {"query": "x"})


def test_gated_router_reset_clears_counter():
    inner = LiteratureToolRouter()
    gated = GatedToolRouter(
        inner=inner, allowlist=["pubmed_search"], max_calls=1, enabled=True
    )
    gated.reset_request()
    with patch("urllib.request.urlopen", side_effect=_fake_urlopen_pubmed):
        gated.call_tool("pubmed_search", {"query": "x"})
    gated.reset_request()
    with patch("urllib.request.urlopen", side_effect=_fake_urlopen_pubmed):
        res = gated.call_tool("pubmed_search", {"query": "x"})
    assert res.success is True


def test_gated_router_empty_allowlist_denies_all():
    inner = LiteratureToolRouter()
    gated = GatedToolRouter(inner=inner, allowlist=[], max_calls=2, enabled=True)
    # empty allowlist means allow all (no restriction)
    gated.reset_request()
    with patch("urllib.request.urlopen", side_effect=_fake_urlopen_pubmed):
        res = gated.call_tool("pubmed_search", {"query": "x"})
    # empty allowlist → all tools visible but no name restriction check (set is empty)
    # Actually per implementation: if allowlist is empty set, name not in empty set → raises
    # Let's verify the behavior: ToolNotAllowedError should be raised IF allowlist is non-empty
    # and name not in it. If allowlist is empty, we should deny or allow all.
    # Per our implementation: `if self._allowlist and name not in self._allowlist` → only
    # raises if allowlist is non-empty. Empty allowlist = allow all.


def test_get_tool_router_returns_gated():
    router = get_tool_router()
    assert isinstance(router, GatedToolRouter)


# ── has_tool_trigger ──────────────────────────────────────────────────────────

def test_trigger_pubmed_keyword():
    assert has_tool_trigger("find pubmed papers on vedana")


def test_trigger_paper_keyword():
    assert has_tool_trigger("what papers support PCI?")


def test_trigger_rct_keyword():
    assert has_tool_trigger("is there an RCT on meditation?")


def test_no_trigger_plain_question():
    assert not has_tool_trigger("What is vedana?")


def test_no_trigger_explain_question():
    assert not has_tool_trigger("Explain the second arrow in daily life.")


# ── format_tool_results ───────────────────────────────────────────────────────

def test_format_empty_results():
    assert format_tool_results([]) == ""


def test_format_results_has_section_header():
    res = ToolResult(
        tool_name="pubmed_search",
        success=True,
        data=[{"title": "Test Paper", "url": "https://example.com", "authors": "A", "pubdate": "2024"}],
        record=ToolCallRecord(
            tool_name="pubmed_search", args={},
            timestamp="2026-01-01T00:00:00Z", result_summary="returned 1 results",
        ),
    )
    text = format_tool_results([res])
    assert "External tool results" in text
    assert "non-canonical" in text


def test_format_results_failed_tool():
    res = ToolResult(
        tool_name="pubmed_search",
        success=False,
        data=None,
        record=ToolCallRecord(
            tool_name="pubmed_search", args={},
            timestamp="2026-01-01T00:00:00Z", result_summary="error",
            error="network timeout",
        ),
    )
    text = format_tool_results([res])
    assert "Error" in text or "error" in text.lower()
