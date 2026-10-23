"""Fixture-first source ingestion for `oss_opportunities`.

Every loader here builds `OpenSourceRepositoryCandidateV1` records from
already-fetched, already-local JSON (manual seed lists, Trendshift
snapshot fixtures, Star History starmap fixtures) with zero network I/O by
default. The one exception, `import_from_trendshift_live_scan`, performs a
single bounded HTTP GET per timeframe against Trendshift's public trending
page -- it is never called by this repository's test suite and requires
the CLI's explicit `--allow-live-network` flag before it is ever reached
(see `export_oss_opportunities._cmd_live_trendshift_scan`). Its own HTML
parsing logic (`_parse_trendshift_html`) is a pure function, fully
testable against a synthetic HTML fixture without any network access.

No loader here clones a repository, installs a dependency, or executes
external code. No loader redistributes a raw Trendshift Signal API
payload (mission rule 13) -- the paid Signal API is not implemented in
this milestone at all; `trendshift_signal` exists in `ALLOWED_SOURCE`
only so a future, explicitly-gated integration has a place to write
records without changing the schema.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Union

from dataclasses import fields as _dataclass_fields

from oss_opportunities.repository_candidate import OpenSourceRepositoryCandidateV1
from oss_opportunities.validation import OssOpportunityValidationError

_CANDIDATE_FIELDS = frozenset(f.name for f in _dataclass_fields(OpenSourceRepositoryCandidateV1))
# Set by the loader itself; a seed entry may not override observation identity.
_SEED_RESERVED_FIELDS = frozenset({"candidate_id", "source", "source_timeframe", "source_snapshot_date", "schema_version"})

_ALLOWED_TRENDSHIFT_TIMEFRAMES = ("daily", "weekly", "monthly", "yearly")
_ALLOWED_STARMAP_CATEGORIES = ("frontend", "backend", "data", "infra")
_LIVE_SCAN_TIMEOUT_S = 10
_LIVE_SCAN_LIMIT_PER_TIMEFRAME = 20


class TrendshiftLiveScanError(RuntimeError):
    """Raised when a live Trendshift scan fails to fetch or parse a page --
    always caught and reported cleanly by the CLI, never silently
    swallowed into a fabricated result."""


class LiveNetworkNotAllowedError(RuntimeError):
    """Raised if a live-network function is ever called without the
    caller already having gated it (defense in depth -- the CLI checks
    `--allow-live-network` first, this is a second, structural check)."""


def _read_json(path: Union[str, Path]) -> Any:
    resolved = Path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"fixture file not found: {path}")
    return json.loads(resolved.read_text(encoding="utf-8"))


def _default_limitations() -> list[str]:
    return ["metadata-only scouting candidate, not evidence, not a completed integration"]


# ── manual seed ──────────────────────────────────────────────────────────


def import_from_manual_seed(seed_path: Union[str, Path]) -> list[OpenSourceRepositoryCandidateV1]:
    """Reads `{"snapshot_date": "...", "repositories": [...]}` where each
    entry is either a plain `"owner/repo"` string (metadata defaults to
    unknown) or a dict with any of `OpenSourceRepositoryCandidateV1`'s
    fields. Never fetches anything over the network."""
    payload = _read_json(seed_path)
    if not isinstance(payload, dict):
        raise OssOpportunityValidationError("manual seed payload must be a JSON object")
    entries = payload.get("repositories") or payload.get("repos") or []
    if not isinstance(entries, list):
        raise OssOpportunityValidationError("manual seed 'repositories' must be a list")
    snapshot_date = payload.get("snapshot_date", "")

    candidates: list[OpenSourceRepositoryCandidateV1] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, (str, dict)):
            raise OssOpportunityValidationError(f"manual seed entry {index} must be a string or an object")
        if isinstance(entry, str):
            repo_full_name = entry
            fields: dict[str, Any] = {}
        else:
            repo_full_name = entry.get("repo_full_name") or entry.get("repo") or ""
            fields = {k: v for k, v in entry.items() if k not in ("repo_full_name", "repo")}
        if not repo_full_name:
            continue
        if not isinstance(repo_full_name, str):
            raise OssOpportunityValidationError(f"manual seed entry {index} repo_full_name must be a string")
        unknown = sorted(str(k) for k in fields if k not in _CANDIDATE_FIELDS - _SEED_RESERVED_FIELDS and k != "rank")
        if unknown:
            raise OssOpportunityValidationError(f"manual seed entry {index} has unknown fields: {unknown}")
        owner = fields.pop("owner", None) or (repo_full_name.split("/")[0] if "/" in repo_full_name else "")
        name = fields.pop("name", None) or (repo_full_name.split("/")[-1] if "/" in repo_full_name else repo_full_name)
        source_rank = fields.pop("source_rank", None)
        fields.pop("rank", None)
        candidate = OpenSourceRepositoryCandidateV1.make(
            repo_full_name=repo_full_name, source="github_manual_seed", source_timeframe="",
            source_snapshot_date=snapshot_date, name=name, owner=owner, source_rank=source_rank,
            repo_url=fields.pop("repo_url", f"https://github.com/{repo_full_name}"),
            provenance=fields.pop("provenance", f"manual seed list: {seed_path}"),
            limitations=fields.pop("limitations", None) or _default_limitations(),
            **fields,
        )
        candidates.append(candidate)
    return candidates


# ── Trendshift fixture ───────────────────────────────────────────────────


def import_from_trendshift_fixture(fixture_path: Union[str, Path]) -> list[OpenSourceRepositoryCandidateV1]:
    """Reads `{"timeframe": "daily"|"weekly"|"monthly"|"yearly",
    "snapshot_date": "...", "repositories": [{"rank":..., "repo_full_name":
    ..., ...}]}` captured from a Trendshift page snippet. Never fetches
    anything over the network; never embeds a raw Trendshift Signal API
    payload (this is the static-snapshot path, not the Signal API)."""
    payload = _read_json(fixture_path)
    timeframe = payload.get("timeframe", "daily")
    if timeframe not in _ALLOWED_TRENDSHIFT_TIMEFRAMES:
        raise ValueError(f"timeframe {timeframe!r} must be one of {_ALLOWED_TRENDSHIFT_TIMEFRAMES}")
    source = f"trendshift_{timeframe}"
    snapshot_date = payload.get("snapshot_date", "")

    candidates: list[OpenSourceRepositoryCandidateV1] = []
    for entry in payload.get("repositories") or []:
        repo_full_name = entry.get("repo_full_name") or entry.get("repo") or ""
        if not repo_full_name:
            continue
        fields = {k: v for k, v in entry.items() if k not in ("repo_full_name", "repo")}
        owner = fields.pop("owner", None) or (repo_full_name.split("/")[0] if "/" in repo_full_name else "")
        name = fields.pop("name", None) or (repo_full_name.split("/")[-1] if "/" in repo_full_name else repo_full_name)
        source_rank = fields.pop("source_rank", None)
        if source_rank is None:
            source_rank = fields.pop("rank", None)
        else:
            fields.pop("rank", None)
        candidate = OpenSourceRepositoryCandidateV1.make(
            repo_full_name=repo_full_name, source=source, source_timeframe=timeframe,
            source_snapshot_date=snapshot_date, name=name, owner=owner, source_rank=source_rank,
            repo_url=fields.pop("repo_url", f"https://github.com/{repo_full_name}"),
            provenance=fields.pop("provenance", f"Trendshift {timeframe} snapshot fixture: {fixture_path}"),
            limitations=fields.pop("limitations", None) or _default_limitations(),
            **fields,
        )
        candidates.append(candidate)
    return candidates


# ── Star History starmap fixture ─────────────────────────────────────────


def import_from_starmap_fixture(fixture_path: Union[str, Path]) -> list[OpenSourceRepositoryCandidateV1]:
    """Reads `{"category": "frontend"|"backend"|"data"|"infra",
    "snapshot_date": "...", "repositories": [{"repo_full_name": ...,
    "stack_layer": ..., ...}]}` captured from a Star History starmap
    snapshot. Never fetches anything over the network."""
    payload = _read_json(fixture_path)
    category = payload.get("category", "frontend")
    if category not in _ALLOWED_STARMAP_CATEGORIES:
        raise ValueError(f"category {category!r} must be one of {_ALLOWED_STARMAP_CATEGORIES}")
    snapshot_date = payload.get("snapshot_date", "")

    candidates: list[OpenSourceRepositoryCandidateV1] = []
    for entry in payload.get("repositories") or []:
        repo_full_name = entry.get("repo_full_name") or entry.get("repo") or ""
        if not repo_full_name:
            continue
        fields = {k: v for k, v in entry.items() if k not in ("repo_full_name", "repo")}
        stack_layer = fields.pop("stack_layer", category)
        observed_categories = fields.pop("observed_categories", None) or [stack_layer]
        owner = fields.pop("owner", None) or (repo_full_name.split("/")[0] if "/" in repo_full_name else "")
        name = fields.pop("name", None) or (repo_full_name.split("/")[-1] if "/" in repo_full_name else repo_full_name)
        candidate = OpenSourceRepositoryCandidateV1.make(
            repo_full_name=repo_full_name, source="star_history_starmap", source_timeframe=category,
            source_snapshot_date=snapshot_date, name=name, owner=owner,
            repo_url=fields.pop("repo_url", f"https://github.com/{repo_full_name}"),
            observed_categories=observed_categories,
            provenance=fields.pop("provenance", f"Star History starmap ({category}) fixture: {fixture_path}"),
            limitations=fields.pop("limitations", None) or _default_limitations(),
            **fields,
        )
        candidates.append(candidate)
    return candidates


# ── live Trendshift scan (network, explicitly gated by the CLI) ─────────

_REPO_LINK_RE = re.compile(r"github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)")


def _parse_trendshift_html(html_text: str, *, timeframe: str, snapshot_date: str, limit: int = _LIVE_SCAN_LIMIT_PER_TIMEFRAME) -> list[OpenSourceRepositoryCandidateV1]:
    """Pure function, no network -- extracts `owner/repo` GitHub links from
    already-fetched Trendshift HTML in first-seen order. Deliberately
    conservative: only a repo full name and its observed rank are
    recorded (star counts/descriptions are not reliably scrapeable from a
    page snippet without committing to Trendshift's exact markup, so they
    stay unknown rather than being guessed) -- and no raw HTML/JSON is
    embedded in the resulting candidates (mission rule 13's spirit applied
    to the free scan path too, even though rule 13 itself is about the
    paid Signal API)."""
    source = f"trendshift_{timeframe}"
    seen: set[str] = set()
    candidates: list[OpenSourceRepositoryCandidateV1] = []
    for match in _REPO_LINK_RE.finditer(html_text):
        owner, repo = match.group(1), match.group(2)
        if repo.endswith(".git"):
            repo = repo[: -len(".git")]
        repo_full_name = f"{owner}/{repo}"
        # Only Trendshift's own repo link is excluded by owner name -- it
        # is virtually guaranteed to appear in any Trendshift page's own
        # nav/footer chrome. Excluding by "sponsors"/"about"/"features" was
        # too broad: those are plausible real GitHub org names and would
        # incorrectly drop a legitimate trending repository owned by one.
        if repo_full_name in seen or owner.lower() == "trendshift":
            continue
        seen.add(repo_full_name)
        candidates.append(
            OpenSourceRepositoryCandidateV1.make(
                repo_full_name=repo_full_name, source=source, source_timeframe=timeframe,
                source_snapshot_date=snapshot_date, name=repo, owner=owner,
                repo_url=f"https://github.com/{repo_full_name}",
                provenance=f"live Trendshift {timeframe} page scan on {snapshot_date}",
                limitations=[
                    "metadata-only scouting candidate, not evidence, not a completed integration",
                    "live-scanned entry: stars/license/description not reliably extractable from the page snippet and are left unknown",
                ],
            )
        )
        if len(candidates) >= limit:
            break
    return candidates


def import_from_trendshift_live_scan(
    *,
    timeframes: list[str],
    snapshot_date: str = "",
    limit_per_timeframe: int = _LIVE_SCAN_LIMIT_PER_TIMEFRAME,
    allow_live_network: bool = False,
) -> list[OpenSourceRepositoryCandidateV1]:
    """Performs one bounded HTTP GET per timeframe against Trendshift's
    public trending page -- only if `allow_live_network=True` is passed
    explicitly. This is a second, structural gate on top of the CLI's own
    `--allow-live-network` check: any caller that imports this function
    directly (bypassing the CLI) still cannot trigger a real network fetch
    without opting in here too. Never called by this repository's test
    suite. Fails cleanly (`TrendshiftLiveScanError`/
    `LiveNetworkNotAllowedError`) rather than returning a partial/
    fabricated result on any fetch or parse error."""
    if not allow_live_network:
        raise LiveNetworkNotAllowedError(
            "import_from_trendshift_live_scan requires allow_live_network=True -- "
            "this scout never performs live network I/O by default"
        )

    import urllib.error
    import urllib.request
    from datetime import date

    snapshot_date = snapshot_date or date.today().isoformat()
    all_candidates: list[OpenSourceRepositoryCandidateV1] = []
    for timeframe in timeframes:
        if timeframe not in _ALLOWED_TRENDSHIFT_TIMEFRAMES:
            raise ValueError(f"timeframe {timeframe!r} must be one of {_ALLOWED_TRENDSHIFT_TIMEFRAMES}")
        url = f"https://trendshift.io/{timeframe}"
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "NeuroTopology-Sim-oss-opportunities/1"})
            with urllib.request.urlopen(request, timeout=_LIVE_SCAN_TIMEOUT_S) as response:
                html_text = response.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise TrendshiftLiveScanError(f"failed to fetch Trendshift {timeframe} page: {exc}") from exc

        try:
            all_candidates.extend(
                _parse_trendshift_html(html_text, timeframe=timeframe, snapshot_date=snapshot_date, limit=limit_per_timeframe)
            )
        except Exception as exc:
            raise TrendshiftLiveScanError(f"failed to parse Trendshift {timeframe} page: {exc}") from exc

    return all_candidates
