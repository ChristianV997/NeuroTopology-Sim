import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tools.awareness_studio_research.source_resolution import (
    RESOLUTION_STATES,
    ResolutionResult,
    SourceIdentity,
    SourceResolutionLog,
    claim_availability,
    resolve_source_identity,
    score_candidate,
)

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "awareness_source_resolution"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _identity(**overrides) -> SourceIdentity:
    base = dict(source_ref="ref", title="A Paper")
    base.update(overrides)
    return SourceIdentity(**base)


# -- exact DOI ----------------------------------------------------------------

def test_exact_doi_match_is_confirmed():
    claimed = _identity(source_ref="claimed", doi="10.1/x", title="A Paper")
    candidate = _identity(source_ref="candidate", doi="10.1/x", title="A Paper (published version)")
    result = resolve_source_identity(claimed, [candidate])
    assert result.state == "confirmed_identity"
    assert result.matched_candidate_ref == "candidate"
    assert "doi_match" in result.evidence


# -- wrong DOI ------------------------------------------------------------------

def test_wrong_doi_with_no_other_signal_is_disputed():
    claimed = _identity(source_ref="claimed", doi="10.1/wrong", title="Claimed Title")
    candidate = _identity(source_ref="candidate", doi="10.1/different", title="Unrelated Title")
    result = resolve_source_identity(claimed, [candidate])
    assert result.state == "disputed_identity"
    assert result.matched_candidate_ref is None


def test_claimed_confirmed_nonexistent_with_no_candidates_is_disputed():
    claimed = _identity(source_ref="claimed", doi="10.1/ghost", exists=False)
    result = resolve_source_identity(claimed, [])
    assert result.state == "disputed_identity"
    assert "exists_false" in result.evidence


# -- corrected DOI (operator correction) ----------------------------------------

def test_corrected_doi_via_operator_correction_confirms():
    claimed = _identity(source_ref="claimed", doi="10.1/wrong", title="Claimed Title")
    correction = _identity(source_ref="correction", doi="10.1/actual-real-doi", title="Actual Title")
    result = resolve_source_identity(claimed, [], operator_correction=correction)
    assert result.state == "confirmed_identity"
    assert result.matched_candidate_ref == "correction"


def test_operator_correction_without_doi_or_arxiv_is_disputed():
    claimed = _identity(source_ref="claimed", doi="10.1/wrong")
    correction = _identity(source_ref="correction", title="Just a title, no identifier")
    result = resolve_source_identity(claimed, [], operator_correction=correction)
    assert result.state == "disputed_identity"


def test_operator_correction_confirmed_nonexistent_is_disputed():
    claimed = _identity(source_ref="claimed", doi="10.1/wrong")
    correction = _identity(source_ref="correction", doi="10.1/also-fake", exists=False)
    result = resolve_source_identity(claimed, [], operator_correction=correction)
    assert result.state == "disputed_identity"


def test_original_disputed_event_survives_after_correction_is_recorded(tmp_path):
    """Requirement 3: never silently replace a disputed record -- both
    the original disputed attempt and the later corrected confirmation
    must remain individually visible in the append-only log."""
    log = SourceResolutionLog(tmp_path / "events.jsonl")
    claimed = _identity(source_ref="claimed:x", doi="10.1/wrong", title="Claimed Title")
    wrong_candidate = _identity(source_ref="candidate:wrong", doi="10.1/different")

    first = resolve_source_identity(claimed, [wrong_candidate])
    log.record_resolution(original_source_ref="claimed:x", result=first, resolver="agent")
    assert first.state == "disputed_identity"

    correction = _identity(source_ref="correction:real", doi="10.1/actual-real-doi")
    second = resolve_source_identity(claimed, [], operator_correction=correction)
    log.record_resolution(original_source_ref="claimed:x", result=second, resolver="operator")
    assert second.state == "confirmed_identity"

    history = log.history_for("claimed:x")
    assert len(history) == 2
    assert history[0].state == "disputed_identity"
    assert history[1].state == "confirmed_identity"
    assert log.current_resolution("claimed:x").state == "confirmed_identity"


# -- arXiv identity ---------------------------------------------------------------

def test_arxiv_id_match_is_confirmed():
    claimed = _identity(source_ref="claimed", arxiv_id="2609.03987", title="triadic functional connectivity")
    candidate = _identity(
        source_ref="candidate", arxiv_id="2609.03987",
        title="High-Order Triadic Functional Connectivity in the Brain and Beyond",
    )
    result = resolve_source_identity(claimed, [candidate])
    assert result.state == "confirmed_identity"
    assert "arxiv_id_match" in result.evidence


# -- title collision (ambiguous) ---------------------------------------------------

def test_title_collision_between_two_equally_scored_candidates_is_ambiguous():
    claimed = _identity(source_ref="claimed", title="A Very Common Title", authors=("A. One",))
    candidate_a = _identity(source_ref="candidate:a", title="A Very Common Title", authors=("B. Two",))
    candidate_b = _identity(source_ref="candidate:b", title="A Very Common Title", authors=("C. Three",))
    result = resolve_source_identity(claimed, [candidate_a, candidate_b])
    assert result.state == "ambiguous_identity"
    assert result.matched_candidate_ref is None


# -- duplicate source ---------------------------------------------------------------

def test_duplicate_of_caller_supplied_is_duplicate_state():
    claimed = _identity(source_ref="claimed", doi="10.1/x")
    result = resolve_source_identity(claimed, [], duplicate_of="already-resolved-ref")
    assert result.state == "duplicate"
    assert result.matched_candidate_ref == "already-resolved-ref"
    assert claim_availability(result.state) == "available"


def test_superseded_by_caller_supplied_is_superseded_state():
    claimed = _identity(source_ref="claimed", doi="10.1/x")
    result = resolve_source_identity(claimed, [], superseded_by="newer-ref")
    assert result.state == "superseded"
    assert claim_availability(result.state) == "available"


# -- disputed source (weak-only signal) ----------------------------------------------

def test_weak_signal_only_is_disputed_not_confirmed():
    claimed = _identity(source_ref="claimed", title="Some Title", journal="Journal X", publication_date="2026")
    candidate = _identity(
        source_ref="candidate", title="A Completely Different Title",
        journal="Journal X", publication_date="2026-05",
    )
    result = resolve_source_identity(claimed, [candidate])
    assert result.state == "disputed_identity"
    assert claim_availability(result.state) == "unavailable"


def test_no_candidates_and_no_correction_is_unavailable():
    claimed = _identity(source_ref="claimed", title="An Unchecked Paper")
    result = resolve_source_identity(claimed, [])
    assert result.state == "unavailable"
    assert claim_availability(result.state) == "unavailable"


# -- claim availability gating (requirement 5) ---------------------------------------

def test_claim_availability_matches_every_state():
    available_states = {"confirmed_identity", "duplicate", "superseded"}
    for state in RESOLUTION_STATES:
        expected = "available" if state in available_states else "unavailable"
        assert claim_availability(state) == expected


def test_claim_availability_rejects_unknown_state():
    with pytest.raises(ValueError):
        claim_availability("not-a-real-state")


# -- five source families fixture (requirement 4) -------------------------------------

def _load_families() -> list[dict]:
    return json.loads((FIXTURES_DIR / "five_source_families.json").read_text())["families"]


@pytest.mark.parametrize("family", _load_families(), ids=lambda f: f["label"])
def test_five_source_families_resolve_as_expected(family):
    claimed = SourceIdentity.from_dict(family["claimed"])
    candidates = [SourceIdentity.from_dict(c) for c in family.get("candidates", [])]

    if "operator_correction" in family:
        without = resolve_source_identity(claimed, candidates)
        assert without.state == family["expected_state_without_correction"]

        correction = SourceIdentity.from_dict(family["operator_correction"])
        with_correction = resolve_source_identity(claimed, [], operator_correction=correction)
        assert with_correction.state == family["expected_state_with_correction"]
    else:
        result = resolve_source_identity(claimed, candidates)
        assert result.state == family["expected_state"]


def test_five_source_families_claim_availability_matches_resolution():
    for family in _load_families():
        claimed = SourceIdentity.from_dict(family["claimed"])
        candidates = [SourceIdentity.from_dict(c) for c in family.get("candidates", [])]
        expected_state = family.get("expected_state") or family["expected_state_without_correction"]
        result = resolve_source_identity(claimed, candidates)
        assert result.state == expected_state
        if expected_state in ("disputed_identity", "ambiguous_identity", "unavailable"):
            assert claim_availability(result.state) == "unavailable"


# -- no-network fixture mode ------------------------------------------------------------

def test_no_network_fixture_mode(tmp_path, monkeypatch):
    def _no_network(*args, **kwargs):
        raise AssertionError("network access attempted during offline resolution")

    monkeypatch.setattr(socket, "socket", _no_network)

    log = SourceResolutionLog(tmp_path / "events.jsonl")
    for family in _load_families():
        claimed = SourceIdentity.from_dict(family["claimed"])
        candidates = [SourceIdentity.from_dict(c) for c in family.get("candidates", [])]
        result = resolve_source_identity(claimed, candidates)
        log.record_resolution(original_source_ref=claimed.source_ref, result=result)
    assert len(log.all_current_resolutions()) == len(_load_families())


def test_module_import_touches_no_network(monkeypatch):
    def _no_network(*args, **kwargs):
        raise AssertionError("network access attempted merely by importing source_resolution.py")

    monkeypatch.setattr(socket, "socket", _no_network)
    import importlib

    import tools.awareness_studio_research.source_resolution as module

    importlib.reload(module)


# -- deterministic event log --------------------------------------------------------------

def test_deterministic_event_log_repeat_writes(tmp_path):
    log = SourceResolutionLog(tmp_path / "events.jsonl")
    claimed = _identity(source_ref="claimed:det", doi="10.1/x")
    candidate = _identity(source_ref="candidate:det", doi="10.1/x")
    result = resolve_source_identity(claimed, [candidate])

    snapshots = set()
    for _ in range(10):
        another_log_path = tmp_path / "det_check.jsonl"
        another_log_path.unlink(missing_ok=True)
        det_log = SourceResolutionLog(another_log_path)
        event = det_log.record_resolution(
            original_source_ref="claimed:det", result=result, resolver="agent", date="2026-09-08T00:00:00+00:00",
        )
        snapshots.add(json.dumps(event.to_dict(), sort_keys=True))
    assert len(snapshots) == 1


def test_event_log_never_rewrites_prior_lines(tmp_path):
    log = SourceResolutionLog(tmp_path / "events.jsonl")
    claimed = _identity(source_ref="claimed:y", doi="10.1/y")
    result_a = resolve_source_identity(claimed, [])
    log.record_resolution(original_source_ref="claimed:y", result=result_a)
    lines_after_first = log.log_path.read_text().splitlines()

    result_b = resolve_source_identity(claimed, [], duplicate_of="some-other-ref")
    log.record_resolution(original_source_ref="claimed:y", result=result_b)
    lines_after_second = log.log_path.read_text().splitlines()

    assert lines_after_second[: len(lines_after_first)] == lines_after_first
    assert len(lines_after_second) == len(lines_after_first) + 1


def test_isolated_subprocess_cli_resolve(tmp_path):
    claimed_path = tmp_path / "claimed.json"
    candidates_path = tmp_path / "candidates.json"
    log_path = tmp_path / "events.jsonl"

    claimed_path.write_text(json.dumps({"source_ref": "claimed:cli", "doi": "10.1/cli-x", "title": "CLI Paper"}))
    candidates_path.write_text(json.dumps([{"source_ref": "candidate:cli", "doi": "10.1/cli-x", "title": "CLI Paper (v2)"}]))

    result = subprocess.run(
        [
            sys.executable, "scripts/resolve_awareness_sources.py", "--log", str(log_path),
            "resolve", "--claimed", str(claimed_path), "--candidates", str(candidates_path),
        ],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["resolution"]["state"] == "confirmed_identity"
    assert payload["claim_availability"] == "available"


def test_no_heavy_import_in_source_resolution_module():
    script = (
        "import sys; "
        "import tools.awareness_studio_research.source_resolution as m; "
        "heavy = {'numpy', 'scipy', 'sklearn', 'mne', 'torch', 'pandas'}; "
        "print('LOADED_HEAVY=' + ','.join(sorted(heavy & set(sys.modules))))"
    )
    result = subprocess.run([sys.executable, "-c", script], cwd=REPO_ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    loaded = next(line for line in result.stdout.splitlines() if line.startswith("LOADED_HEAVY=")).split("=", 1)[1]
    assert loaded == ""
