"""ds001787 behavioral (probe rating) parsing and cross-clock alignment.

ds001787's actual depth-of-meditation/mind-wandering/tiredness ratings (0-3 scale)
are NOT in the standard BIDS `_events.tsv` files -- those only carry button-press
IDENTITY codes (value=2/4/8, "Response 1/2/3", per `task-meditation_events.json`'s
own field description: "this may be a response to question 1, 2 or 3"). The real
ratings live in a non-BIDS-standard file added later
(`code/MW_Current_TextFileBIDS.zip`, per CHANGES 1.1.0), one `.txt` per
subject/session, format:

    MW question asked at time  91.1 second
    Key 2 (code 2) pressed at time  94.1 seconds, status 1
    Key 1 (code 1) pressed at time  98.5 seconds, status 2
    Key 0 (code 0) pressed at time 101.7 seconds, status 3

`status` 1/2/3 = Q1 (depth of meditation) / Q2 (depth of mind-wandering) / Q3
(tiredness), per the source paper's design (Brandmeyer & Delorme 2018) -- this
question-identity mapping is NOT independently re-derivable from the text file
itself (it has no per-status question text, only the numeric status), so it is
taken from the published methods, not verified against this release's raw data.
`code` 0-3 is the actual rating (confirmed via direct inspection: values observed
were {0,1,2,3} plus one single anomalous 4 out of ~2983 responses, treated as
noise, not a scale redefinition).

CRITICAL, VERIFIED-BEFORE-CODING FINDING: the behavioral file's "MW question asked
at time" timestamps are on a DIFFERENT clock than the EEG recording's `_events.tsv`
"stimulus" onsets -- not a shared frame. For most subject/sessions this is a
near-constant, small (0-100s) per-session offset (a fixed hardware/software
start-lag), and after correcting for it, matching is exact. But for 5 of 41
subject/sessions checked (sub-003/ses-01, sub-004/ses-01, sub-013/ses-01,
sub-014/ses-01, sub-022/ses-02), no offset in a wide search range (-300s to
+300s) produces a usable match (best match rate <=0.21) -- the two logs are not
simply offset for these sessions (verified: even a single-dropped-probe hypothesis
with per-probe residuals up to 137s does not explain sub-013/ses-01). This is
reported, not silently worked around: those sessions are excluded from any
probe-locked (depth-rating) use, flagged with `alignment_usable=False`.
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_MW_QUESTION_RE = re.compile(r"MW question asked at time\s+([\d.]+) second")
_RESPONSE_RE = re.compile(r"code (\d+)\) pressed at time\s+([\d.]+) seconds, status (\d+)")

# Match-quality gate: a subject/session's behavioral log is only trusted for
# probe-locked (Analysis B) use if at least this fraction of its MW-question
# timestamps find an events.tsv stimulus onset within ALIGNMENT_TOLERANCE_S at
# the best-fit offset. Chosen from the empirical bimodal split observed on this
# dataset: usable sessions cluster at match_rate=1.00, unusable ones at <=0.21 --
# there is no middle ground, so 0.9 cleanly separates the two populations without
# being a sensitive threshold choice.
ALIGNMENT_MATCH_RATE_GATE = 0.9
ALIGNMENT_TOLERANCE_S = 3.0
_OFFSET_SEARCH_RANGE_S = (-300.0, 300.0)
_OFFSET_SEARCH_STEP_S = 0.2


@dataclass
class ProbeRating:
    mw_question_time_s: float  # on the behavioral file's own clock
    depth_of_meditation: int | None  # status=1 code
    depth_of_mind_wandering: int | None  # status=2 code
    tiredness: int | None  # status=3 code


@dataclass
class AlignedProbe:
    stim_onset_s: float  # on the EEG recording's own clock (events.tsv-relative)
    depth_of_meditation: int | None
    depth_of_mind_wandering: int | None
    tiredness: int | None


def parse_behavioral_zip(zip_bytes: bytes) -> dict[str, dict[str, list[ProbeRating]]]:
    """Parse MW_Current_TextFileBIDS.zip into {subject_num_str: {session_num_str: [ProbeRating]}}.

    subject_num_str/session_num_str are the zero-padded numeric strings used in the
    zip's own filenames (e.g. "01", "1"), NOT yet mapped to sub-XXX/ses-XX BIDS IDs
    -- that mapping happens in `load_ds001787_behavioral` below.
    """
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    out: dict[str, dict[str, list[ProbeRating]]] = {}
    for name in zf.namelist():
        if not (name.startswith("MW_Current_TextFileBIDS/sub") and name.endswith("_info.txt")):
            continue
        m = re.match(r"MW_Current_TextFileBIDS/sub(\d+)_?(\d?)_?_?info\.txt", name)
        if not m:
            continue
        subnum, ses_digit = m.group(1), (m.group(2) or "1")
        content = zf.read(name).decode("utf-8", errors="replace")
        probes: list[ProbeRating] = []
        cur_time = None
        cur = {"1": None, "2": None, "3": None}
        for line in content.splitlines():
            qm = _MW_QUESTION_RE.search(line)
            if qm:
                if cur_time is not None:
                    probes.append(ProbeRating(cur_time, cur["1"], cur["2"], cur["3"]))
                cur_time = float(qm.group(1))
                cur = {"1": None, "2": None, "3": None}
                continue
            rm = _RESPONSE_RE.search(line)
            if rm and cur_time is not None:
                code, _t, status = rm.groups()
                if status in cur:
                    cur[status] = int(code)
        if cur_time is not None:
            probes.append(ProbeRating(cur_time, cur["1"], cur["2"], cur["3"]))
        out.setdefault(subnum, {})[ses_digit] = probes
    return out


def _best_offset_and_matches(
    stim_onsets: list[float], mw_times: list[float],
    tol: float = ALIGNMENT_TOLERANCE_S,
    search_range: tuple[float, float] = _OFFSET_SEARCH_RANGE_S,
    step: float = _OFFSET_SEARCH_STEP_S,
) -> tuple[float, int]:
    """Grid-search the constant offset (added to mw_times) maximizing nearest-neighbor
    matches to stim_onsets within `tol`. Returns (best_offset, n_matched)."""
    stim = np.asarray(stim_onsets, dtype=float)
    mw = np.asarray(mw_times, dtype=float)
    if stim.size == 0 or mw.size == 0:
        return 0.0, 0
    best_offset, best_count = 0.0, -1
    for off in np.arange(search_range[0], search_range[1], step):
        shifted = mw + off
        count = int(sum(1 for t in shifted if np.min(np.abs(stim - t)) <= tol))
        if count > best_count:
            best_count, best_offset = count, float(off)
    return best_offset, best_count


def align_probes_to_stim_onsets(
    stim_onsets: list[float], probes: list[ProbeRating],
) -> tuple[list[AlignedProbe], dict]:
    """Match each behavioral probe to its nearest events.tsv stimulus onset at the
    best-fit constant offset. Returns (aligned_probes, diagnostics) where diagnostics
    has offset_s, match_rate, n_stim, n_probes, usable (bool, gated by
    ALIGNMENT_MATCH_RATE_GATE).
    """
    mw_times = [p.mw_question_time_s for p in probes]
    offset, n_matched = _best_offset_and_matches(stim_onsets, mw_times)
    match_rate = (n_matched / len(mw_times)) if mw_times else 0.0
    usable = match_rate >= ALIGNMENT_MATCH_RATE_GATE

    aligned: list[AlignedProbe] = []
    if usable:
        stim = np.asarray(stim_onsets, dtype=float)
        for p in probes:
            shifted = p.mw_question_time_s + offset
            idx = int(np.argmin(np.abs(stim - shifted)))
            if abs(stim[idx] - shifted) <= ALIGNMENT_TOLERANCE_S:
                aligned.append(AlignedProbe(
                    stim_onset_s=float(stim[idx]),
                    depth_of_meditation=p.depth_of_meditation,
                    depth_of_mind_wandering=p.depth_of_mind_wandering,
                    tiredness=p.tiredness,
                ))
    diagnostics = {
        "offset_s": offset, "match_rate": match_rate,
        "n_stim": len(stim_onsets), "n_probes": len(probes),
        "n_matched": n_matched, "usable": usable,
    }
    return aligned, diagnostics


def load_ds001787_behavioral(zip_path: str) -> dict[str, dict[str, list[ProbeRating]]]:
    """Load and parse a local copy of MW_Current_TextFileBIDS.zip."""
    data = Path(zip_path).read_bytes()
    return parse_behavioral_zip(data)
