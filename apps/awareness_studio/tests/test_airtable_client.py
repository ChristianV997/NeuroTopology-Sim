"""
Tests for AirtableClient — all offline, urllib mocked.
No Airtable API key or network access required.
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from awareness_studio.integrations.airtable_client import (
    AirtableClient,
    AirtableError,
)
import urllib.error


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_client(enabled: bool = False) -> AirtableClient:
    return AirtableClient(api_key="test_key", base_id="appTEST123", enabled=enabled)


def _fake_response(data: dict) -> MagicMock:
    mock = MagicMock()
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    mock.read.return_value = json.dumps(data).encode()
    return mock


_RECORDS_PAGE_1 = {
    "records": [
        {"id": "rec1", "fields": {"run_id": "run-a", "mode": "EXPLAIN"}},
        {"id": "rec2", "fields": {"run_id": "run-b", "mode": "TEACH"}},
    ],
    "offset": "page2token",
}

_RECORDS_PAGE_2 = {
    "records": [
        {"id": "rec3", "fields": {"run_id": "run-c", "mode": "MATRIX"}},
    ],
}

_CREATED_RECORD = {
    "id": "recNEW",
    "fields": {"run_id": "run-x", "mode": "EXPLAIN"},
}

_UPDATED_RECORD = {
    "id": "rec1",
    "fields": {"run_id": "run-a", "mode": "TEACH"},
}


# ── Construction ──────────────────────────────────────────────────────────────

def test_client_missing_api_key_raises():
    with pytest.raises(ValueError, match="AIRTABLE_API_KEY"):
        AirtableClient(api_key="", base_id="appTEST")


def test_client_missing_base_id_raises():
    with pytest.raises(ValueError, match="AIRTABLE_BASE_ID"):
        AirtableClient(api_key="key", base_id="")


def test_client_constructed_ok():
    c = _make_client()
    assert c is not None


# ── list_records (pagination) ─────────────────────────────────────────────────

def test_list_records_single_page():
    c = _make_client()
    pages = [_RECORDS_PAGE_2]  # no offset → one page
    call_count = 0

    def fake_urlopen(req, timeout=15):
        nonlocal call_count
        call_count += 1
        return _fake_response(pages[0])

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        records = c.list_records("Runs")

    assert len(records) == 1
    assert call_count == 1


def test_list_records_pagination():
    c = _make_client()
    responses = [_RECORDS_PAGE_1, _RECORDS_PAGE_2]
    call_count = 0

    def fake_urlopen(req, timeout=15):
        nonlocal call_count
        resp = responses[call_count]
        call_count += 1
        return _fake_response(resp)

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        records = c.list_records("Runs")

    assert len(records) == 3
    assert call_count == 2


def test_list_records_max_records_cap():
    c = _make_client()

    def fake_urlopen(req, timeout=15):
        return _fake_response(_RECORDS_PAGE_1)

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        records = c.list_records("Runs", max_records=1)

    assert len(records) == 1


def test_list_records_with_filter():
    c = _make_client()
    captured_url = []

    def fake_urlopen(req, timeout=15):
        captured_url.append(str(req.full_url if hasattr(req, "full_url") else req))
        return _fake_response(_RECORDS_PAGE_2)

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        c.list_records("Runs", filter_formula="{run_id}='run-a'")

    assert "filterByFormula" in captured_url[0]


# ── find_by_field ─────────────────────────────────────────────────────────────

def test_find_by_field_found():
    c = _make_client()

    def fake_urlopen(req, timeout=15):
        return _fake_response({"records": [{"id": "rec1", "fields": {"run_id": "run-a"}}]})

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = c.find_by_field("Runs", "run_id", "run-a")

    assert result is not None
    assert result["id"] == "rec1"


def test_find_by_field_not_found():
    c = _make_client()

    def fake_urlopen(req, timeout=15):
        return _fake_response({"records": []})

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = c.find_by_field("Runs", "run_id", "nonexistent")

    assert result is None


# ── Write gating ──────────────────────────────────────────────────────────────

def test_create_record_disabled_raises():
    c = _make_client(enabled=False)
    with pytest.raises(PermissionError, match="AIRTABLE_ENABLED=false"):
        c.create_record("Runs", {"run_id": "x"})


def test_update_record_disabled_raises():
    c = _make_client(enabled=False)
    with pytest.raises(PermissionError, match="AIRTABLE_ENABLED=false"):
        c.update_record("Runs", "rec1", {"mode": "TEACH"})


def test_upsert_disabled_raises():
    c = _make_client(enabled=False)
    with pytest.raises(PermissionError, match="AIRTABLE_ENABLED=false"):
        c.upsert_by_field("Runs", "run_id", "x", {"mode": "TEACH"})


# ── create_record ─────────────────────────────────────────────────────────────

def test_create_record_enabled():
    c = _make_client(enabled=True)

    def fake_urlopen(req, timeout=15):
        return _fake_response(_CREATED_RECORD)

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = c.create_record("Runs", {"run_id": "run-x", "mode": "EXPLAIN"})

    assert result["id"] == "recNEW"


def test_create_record_sends_post():
    c = _make_client(enabled=True)
    captured = []

    def fake_urlopen(req, timeout=15):
        captured.append(req.get_method())
        return _fake_response(_CREATED_RECORD)

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        c.create_record("Runs", {"run_id": "y"})

    assert captured[0] == "POST"


# ── update_record ─────────────────────────────────────────────────────────────

def test_update_record_enabled():
    c = _make_client(enabled=True)

    def fake_urlopen(req, timeout=15):
        return _fake_response(_UPDATED_RECORD)

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = c.update_record("Runs", "rec1", {"mode": "TEACH"})

    assert result["id"] == "rec1"


def test_update_record_sends_patch():
    c = _make_client(enabled=True)
    captured = []

    def fake_urlopen(req, timeout=15):
        captured.append(req.get_method())
        return _fake_response(_UPDATED_RECORD)

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        c.update_record("Runs", "rec1", {"mode": "TEACH"})

    assert captured[0] == "PATCH"


# ── upsert_by_field ───────────────────────────────────────────────────────────

def test_upsert_creates_when_not_found():
    c = _make_client(enabled=True)
    call_methods = []

    def fake_urlopen(req, timeout=15):
        method = req.get_method()
        call_methods.append(method)
        if method == "GET":
            return _fake_response({"records": []})
        return _fake_response(_CREATED_RECORD)

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = c.upsert_by_field("Runs", "run_id", "new-run", {"mode": "EXPLAIN"})

    assert "POST" in call_methods
    assert result["id"] == "recNEW"


def test_upsert_updates_when_found():
    c = _make_client(enabled=True)
    call_methods = []

    def fake_urlopen(req, timeout=15):
        method = req.get_method()
        call_methods.append(method)
        if method == "GET":
            return _fake_response({"records": [{"id": "rec1", "fields": {"run_id": "run-a"}}]})
        return _fake_response(_UPDATED_RECORD)

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = c.upsert_by_field("Runs", "run_id", "run-a", {"mode": "TEACH"})

    assert "PATCH" in call_methods


# ── HTTP errors ───────────────────────────────────────────────────────────────

def test_http_error_raises_airtable_error():
    c = _make_client()
    err = urllib.error.HTTPError(
        url="https://api.airtable.com/v0/appTEST/Runs",
        code=404,
        msg="Not Found",
        hdrs=None,
        fp=None,
    )
    err.read = lambda: b'{"error": {"type": "TABLE_NOT_FOUND"}}'

    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(AirtableError) as exc_info:
            c.list_records("Runs")

    assert exc_info.value.status == 404
    assert "TABLE_NOT_FOUND" in exc_info.value.body
