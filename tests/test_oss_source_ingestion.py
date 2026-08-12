"""Tests for `oss_opportunities.source_ingestion` -- fixture loaders plus
the pure (no-network) Trendshift HTML parser. The live-network fetch path
(`import_from_trendshift_live_scan`'s `urllib.request.urlopen` call) is
never exercised here; only `_parse_trendshift_html`, its pure parsing
half, is tested directly against a synthetic HTML string."""
from __future__ import annotations

import json

import pytest

from oss_opportunities.source_ingestion import (
    _parse_trendshift_html,
    import_from_manual_seed,
    import_from_starmap_fixture,
    import_from_trendshift_fixture,
)


def test_manual_seed_supports_plain_strings_and_dicts(tmp_path):
    payload = {
        "snapshot_date": "2026-08-12",
        "repositories": [
            "docker/docker",
            {"repo_full_name": "microsoft/markitdown", "license_spdx": "MIT", "license_name": "MIT License"},
        ],
    }
    path = tmp_path / "seed.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    candidates = import_from_manual_seed(path)
    assert len(candidates) == 2
    assert candidates[0].repo_full_name == "docker/docker"
    assert candidates[0].source == "github_manual_seed"
    assert candidates[1].license_spdx == "MIT"
    for c in candidates:
        assert c.validate() == []


def test_trendshift_fixture_maps_rank_to_source_rank(tmp_path):
    payload = {
        "timeframe": "weekly", "snapshot_date": "2026-08-12",
        "repositories": [{"repo_full_name": "a/b", "rank": 3, "license_spdx": "MIT", "license_name": "MIT License"}],
    }
    path = tmp_path / "trendshift.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    candidates = import_from_trendshift_fixture(path)
    assert candidates[0].source == "trendshift_weekly"
    assert candidates[0].source_rank == 3
    assert candidates[0].validate() == []


def test_trendshift_fixture_rejects_invalid_timeframe(tmp_path):
    payload = {"timeframe": "hourly", "repositories": []}
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        import_from_trendshift_fixture(path)


def test_starmap_fixture_maps_category_and_stack_layer(tmp_path):
    payload = {
        "category": "backend", "snapshot_date": "2026-08-12",
        "repositories": [{"repo_full_name": "honojs/hono", "license_spdx": "MIT", "license_name": "MIT License"}],
    }
    path = tmp_path / "starmap.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    candidates = import_from_starmap_fixture(path)
    assert candidates[0].source == "star_history_starmap"
    assert candidates[0].source_timeframe == "backend"
    assert "backend" in candidates[0].observed_categories


def test_starmap_fixture_rejects_invalid_category(tmp_path):
    payload = {"category": "not_a_real_category", "repositories": []}
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        import_from_starmap_fixture(path)


def test_parse_trendshift_html_extracts_repo_links_no_network():
    html = """
    <html><body>
    <a href="https://github.com/microsoft/markitdown">markitdown</a>
    <a href="https://github.com/D4Vinci/Scrapling">Scrapling</a>
    <a href="https://github.com/some/repo.git">repo</a>
    </body></html>
    """
    candidates = _parse_trendshift_html(html, timeframe="daily", snapshot_date="2026-08-12", limit=20)
    names = [c.repo_full_name for c in candidates]
    assert names == ["microsoft/markitdown", "D4Vinci/Scrapling", "some/repo"]
    for c in candidates:
        assert c.validate() == []
        assert c.source == "trendshift_daily"


def test_parse_trendshift_html_deduplicates_and_excludes_site_chrome_links():
    html = """
    <a href="https://github.com/microsoft/markitdown">a</a>
    <a href="https://github.com/microsoft/markitdown">dup</a>
    <a href="https://github.com/trendshift/about">about</a>
    """
    candidates = _parse_trendshift_html(html, timeframe="daily", snapshot_date="2026-08-12", limit=20)
    assert len(candidates) == 1
    assert candidates[0].repo_full_name == "microsoft/markitdown"


def test_parse_trendshift_html_respects_limit():
    html = "".join(f'<a href="https://github.com/owner{i}/repo{i}">x</a>' for i in range(30))
    candidates = _parse_trendshift_html(html, timeframe="daily", snapshot_date="2026-08-12", limit=5)
    assert len(candidates) == 5


def test_parse_trendshift_html_handles_empty_input():
    candidates = _parse_trendshift_html("", timeframe="daily", snapshot_date="2026-08-12")
    assert candidates == []
