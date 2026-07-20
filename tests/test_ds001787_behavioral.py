"""Tests for ds001787's behavioral (probe rating) parsing and cross-clock alignment.

These verify the exact logic that was validated against the REAL ds001787 data
during Step 0 (before any pipeline code was written): sub-001/ses-01 aligns
cleanly (27/27 matched, offset~14.6s); sub-013/ses-01 does not (best match rate
~0.21 across a -300..+300s search) and must be flagged unusable, not silently
forced.
"""
from __future__ import annotations

import io
import zipfile

from sciencer_d.btc_icft.level_m.ds001787_behavioral import (
    ALIGNMENT_MATCH_RATE_GATE,
    align_probes_to_stim_onsets,
    parse_behavioral_zip,
)

_SUB01_TXT = """MW question asked at time  54.1 second
Key 1 (code 1) pressed at time  58.4 seconds, status 1
Key 1 (code 1) pressed at time  62.5 seconds, status 2
Key 0 (code 0) pressed at time  66.3 seconds, status 3
MW question asked at time 162.5 second
Key 1 (code 1) pressed at time 165.7 seconds, status 1
Key 2 (code 2) pressed at time 168.3 seconds, status 2
Key 0 (code 0) pressed at time 170.5 seconds, status 3
"""


def _make_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_parse_behavioral_zip_extracts_status_mapped_ratings():
    zbytes = _make_zip({"MW_Current_TextFileBIDS/sub01_info.txt": _SUB01_TXT})
    parsed = parse_behavioral_zip(zbytes)
    assert "01" in parsed
    assert "1" in parsed["01"]
    probes = parsed["01"]["1"]
    assert len(probes) == 2
    assert probes[0].mw_question_time_s == 54.1
    assert probes[0].depth_of_meditation == 1  # status=1 code
    assert probes[0].depth_of_mind_wandering == 1  # status=2 code
    assert probes[0].tiredness == 0  # status=3 code


def test_parse_behavioral_zip_handles_session_2_and_double_underscore_naming():
    zbytes = _make_zip({
        "MW_Current_TextFileBIDS/sub02__info.txt": _SUB01_TXT,  # ses-01, double underscore (real filename quirk)
        "MW_Current_TextFileBIDS/sub02_2_info.txt": _SUB01_TXT,  # ses-02
        "__MACOSX/MW_Current_TextFileBIDS/._sub02_info.txt": "junk",  # must be ignored
    })
    parsed = parse_behavioral_zip(zbytes)
    assert set(parsed["02"].keys()) == {"1", "2"}


def test_alignment_succeeds_with_small_constant_offset():
    """Mirrors real sub-001/ses-01: stim onsets = mw times + ~14-15s offset."""
    mw_times = [54.1, 162.5, 267.5, 344.8]
    offset = 14.6
    stim_onsets = [t + offset for t in mw_times]
    zbytes = _make_zip({"MW_Current_TextFileBIDS/sub01_info.txt": _SUB01_TXT})
    probes = parse_behavioral_zip(zbytes)["01"]["1"]
    # extend probes list length to match stim_onsets for this synthetic case
    from sciencer_d.btc_icft.level_m.ds001787_behavioral import ProbeRating
    probes = [ProbeRating(t, 1, 1, 0) for t in mw_times]

    aligned, diag = align_probes_to_stim_onsets(stim_onsets, probes)
    assert diag["usable"] is True
    assert diag["match_rate"] == 1.0
    assert len(aligned) == 4
    # with only 4 sparse points, several offsets near the truth match all 4 within
    # tolerance -- exact-offset recovery precision was validated against real
    # 27-probe ds001787 data (sub-001/ses-01) during Step 0, not re-tested here
    assert abs(diag["offset_s"] - offset) < 5.0


def test_alignment_fails_gracefully_when_no_offset_reconciles_logs():
    """Mirrors real sub-013/ses-01: no single offset in the search range explains
    the two time series (verified against actual data before writing this pipeline).
    Must be flagged unusable, not force a bad match.
    """
    from sciencer_d.btc_icft.level_m.ds001787_behavioral import ProbeRating

    stim_onsets = [71.3, 242.1, 281.6, 343.9, 414.1, 476.3, 604.0, 674.8]
    # deliberately non-offset-reconcilable (mirrors real sub-013 structure: deltas
    # between consecutive events don't match between the two logs at all)
    mw_times = [20.1, 158.8, 213.8, 246.3, 321.0, 402.6, 498.4, 635.6]
    probes = [ProbeRating(t, 1, 1, 0) for t in mw_times]

    aligned, diag = align_probes_to_stim_onsets(stim_onsets, probes)
    assert diag["usable"] is False
    assert diag["match_rate"] < ALIGNMENT_MATCH_RATE_GATE
    assert aligned == []  # no windows fabricated from an unreliable alignment
