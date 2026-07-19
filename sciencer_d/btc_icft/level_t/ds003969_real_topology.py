"""Real signal-derived Level T topology for ds003969 (meditation vs thinking).

Direct port of `ds005620_real_topology.py`. `compute_real_topology_for_window`
reads the actual per-channel signal for a window and computes topology via
`eeg_signal_topology.compute_topology_from_channels` (the same real, signal-derived
computation reused by ds005620 and the generic multi-dataset pipeline) -- not a
hash of row_id/metadata text. `compute_fixture_topology_for_window` (hash-based) is
kept only as the explicit, clearly-labeled `--mock-fixture` fallback, exactly as in
the ds005620 module; `--real` never falls back to it (see
`build_level_t_rows_from_m_windows`, copied verbatim including the mutual-exclusivity
contract enforced by the CLI).

BANNED_REPORT_PHRASES is copied verbatim from the ds005620 module (not weakened),
plus two ds003969-relevant additions (`enlightenment proven`, `nirvana confirmed`)
matching the guard added to ds003969_windows.py -- overclaiming risk here is
meditation-tradition-specific, not just consciousness/soul/afterlife generic.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import csv
import hashlib
import json
import sys
from pathlib import Path

from sciencer_d.btc_icft.level_t.eeg_signal_topology import compute_topology_from_channels

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

BANNED_REPORT_PHRASES = (
    "proves consciousness",
    "soul proven",
    "afterlife proven",
    "liberation detected",
    "enlightenment proven",
    "nirvana confirmed",
    "ontology solved",
    "ultimate reality",
    "q equals self",
    "q equals soul",
    "q_abs equals suffering",
    "f_dress equals karma",
)

REQUIRED_M_COLUMNS = [
    "row_id", "subject_id", "session_id", "run_id", "window_id", "task_label",
    "source_file", "window_start_s", "window_end_s",
]


@dataclass
class LevelTRealTopologyRow:
    row_id: str
    subject_id: str
    session_id: str | None
    run_id: str | None
    window_id: str
    task_label: str | None
    q_net: float
    q_abs: float
    f_dress: float
    defect_density: float
    n_triangles: int
    n_valid_triangles: int
    topology_quality: float
    null_method: str
    null_seed: int
    source_file: str
    window_start_s: float
    window_end_s: float
    warnings: list[str]


@dataclass
class LevelTRealTopologyResult:
    dataset_id: str
    n_rows: int
    n_subjects: int
    n_windows: int
    topology_quality_report: dict
    null_placeholder_report: dict
    artifact_alignment_report: dict
    omega_event: dict
    safe_claim: str
    forbidden_claims: list[str]
    warnings: list[str]


def _validate_safe_text(text: str) -> None:
    low = text.lower()
    for phrase in BANNED_REPORT_PHRASES:
        if phrase in low:
            raise ValueError(f"banned phrase detected: {phrase}")


def _h(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)


def load_level_m_window_features(m_windows_dir: str) -> list[dict]:
    p = Path(m_windows_dir) / "features_m.csv"
    if not p.exists():
        raise FileNotFoundError("Level M window features are required. Run run_ds003969_m_real first or use --mock-fixture.")
    with p.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    missing = [c for c in REQUIRED_M_COLUMNS if c not in (rows[0].keys() if rows else [])]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    return rows


def compute_fixture_topology_for_window(m_row: dict, index: int = 0) -> LevelTRealTopologyRow:
    seed_src = f"{m_row.get('row_id')}|{m_row.get('source_file')}|{m_row.get('task_label')}|{m_row.get('window_id')}|{index}"
    hv = _h(seed_src)
    n_triangles = 8 + (hv % 25)
    n_valid = 1 + (hv // 7) % n_triangles
    q_net = round((((hv % 6001) / 1000.0) - 3.0), 6)
    q_abs = round(abs(q_net) + (((hv // 13) % 3000) / 1000.0), 6)
    f_dress = round(max(0.0, q_abs - abs(q_net)), 6)
    defect_density = round(q_abs / max(n_valid, 1), 6)
    topo = round(n_valid / n_triangles, 6)
    return LevelTRealTopologyRow(
        row_id=str(m_row.get("row_id")), subject_id=str(m_row.get("subject_id")),
        session_id=m_row.get("session_id") or None, run_id=m_row.get("run_id") or None,
        window_id=str(m_row.get("window_id")), task_label=m_row.get("task_label") or None,
        q_net=q_net, q_abs=q_abs, f_dress=f_dress, defect_density=defect_density,
        n_triangles=int(n_triangles), n_valid_triangles=int(n_valid), topology_quality=topo,
        null_method="fixture_none", null_seed=int(_h(str(m_row.get("row_id"))) % (2**31 - 1)),
        source_file=str(m_row.get("source_file")),
        window_start_s=float(m_row.get("window_start_s") or 0.0),
        window_end_s=float(m_row.get("window_end_s") or 0.0),
        warnings=[],
    )


def compute_real_topology_for_window(m_row: dict, max_channels: int | None = 16) -> LevelTRealTopologyRow:
    """Compute topology telemetry from the ACTUAL EEG signal for one window.

    Identical logic to ds005620's `compute_real_topology_for_window`: reads real
    per-channel samples and computes topology via `compute_topology_from_channels`.
    Returns a zero/flagged row (not a raised exception) if the source file can't be
    read, matching the generic pipeline's skip-and-report convention.
    """
    from data.bids_ingest import read_window_signal

    row_id = str(m_row.get("row_id"))
    source_file = str(m_row.get("source_file") or "")
    window_start_s = float(m_row.get("window_start_s") or 0.0)
    window_end_s = float(m_row.get("window_end_s") or 0.0)
    warnings: list[str] = []

    def _zero_row(reason: str) -> LevelTRealTopologyRow:
        warnings.append(reason)
        return LevelTRealTopologyRow(
            row_id=row_id, subject_id=str(m_row.get("subject_id")),
            session_id=m_row.get("session_id") or None, run_id=m_row.get("run_id") or None,
            window_id=str(m_row.get("window_id")), task_label=m_row.get("task_label") or None,
            q_net=0.0, q_abs=0.0, f_dress=0.0, defect_density=0.0,
            n_triangles=0, n_valid_triangles=0, topology_quality=0.0,
            null_method="real_none", null_seed=0,
            source_file=source_file, window_start_s=window_start_s, window_end_s=window_end_s,
            warnings=warnings,
        )

    if not source_file or not Path(source_file).exists():
        return _zero_row(f"source file not found: {source_file!r}; topology skipped")

    try:
        channels = read_window_signal(
            source_file, window_start_s, window_end_s, pick="all", max_channels=max_channels
        )
    except ValueError as exc:
        return _zero_row(f"window skipped: {exc}")

    channel_data = [list(map(float, ch)) for ch in channels]
    (
        q_net, q_abs, f_dress, defect_density,
        n_triangles, n_valid_triangles, topology_quality,
    ) = compute_topology_from_channels(channel_data)

    return LevelTRealTopologyRow(
        row_id=row_id, subject_id=str(m_row.get("subject_id")),
        session_id=m_row.get("session_id") or None, run_id=m_row.get("run_id") or None,
        window_id=str(m_row.get("window_id")), task_label=m_row.get("task_label") or None,
        q_net=q_net, q_abs=q_abs, f_dress=f_dress, defect_density=defect_density,
        n_triangles=n_triangles, n_valid_triangles=n_valid_triangles, topology_quality=topology_quality,
        null_method="real_none", null_seed=int(_h(row_id) % (2**31 - 1)),
        source_file=source_file, window_start_s=window_start_s, window_end_s=window_end_s,
        warnings=warnings,
    )


def build_level_t_rows_from_m_windows(
    m_rows: list[dict], mock_fixture: bool = False, real: bool = False
) -> list[LevelTRealTopologyRow]:
    if real:
        return [compute_real_topology_for_window(r) for r in m_rows]
    if not mock_fixture:
        raise ValueError("real EEG topology extraction requires --real or --mock-fixture")
    return [compute_fixture_topology_for_window(r, i) for i, r in enumerate(m_rows)]


def build_topology_quality_report(rows: list[LevelTRealTopologyRow]) -> dict:
    qs = [r.topology_quality for r in rows]
    return {
        "n_rows": len(rows), "n_subjects": len({r.subject_id for r in rows}), "n_windows": len(rows),
        "mean_topology_quality": (sum(qs) / len(qs)) if qs else 0.0,
        "min_topology_quality": min(qs) if qs else 0.0, "max_topology_quality": max(qs) if qs else 0.0,
        "low_quality_rows": [r.row_id for r in rows if r.topology_quality < 0.25 or r.n_valid_triangles <= 0],
        "n_valid_triangles_total": sum(r.n_valid_triangles for r in rows),
        "n_triangles_total": sum(r.n_triangles for r in rows),
        "quality_passed": all(r.topology_quality >= 0.25 and r.n_valid_triangles > 0 for r in rows),
    }


def build_null_placeholder_report(rows: list[LevelTRealTopologyRow]) -> dict:
    return {"status": "placeholder_only", "real_nulls_performed": False, "methods_planned": ["channel_shuffle", "time_reverse", "phase_randomization"], "note": "Null controls are placeholders at Level T extraction; residual benchmark controls run in Issue #54.", "n_rows": len(rows)}


def build_artifact_alignment_report(rows: list[LevelTRealTopologyRow], m_rows: list[dict]) -> dict:
    by_id = {str(r.get("row_id")): r for r in m_rows}
    art = []
    missing = 0
    for r in rows:
        v = by_id.get(r.row_id, {}).get("artifact_score")
        if v in (None, ""):
            missing += 1
        else:
            art.append(float(v))
    return {
        "n_rows": len(rows), "n_matched_m_rows": sum(1 for r in rows if r.row_id in by_id),
        "n_missing_artifact_scores": missing, "mean_artifact_score": (sum(art)/len(art)) if art else 0.0,
        "high_artifact_rows": [r.row_id for r in rows if (by_id.get(r.row_id, {}).get("artifact_score") not in (None, "") and float(by_id[r.row_id]["artifact_score"]) > 0.5)],
        "topology_quality_mean": (sum(r.topology_quality for r in rows)/len(rows)) if rows else 0.0,
        "low_topology_quality_rows": [r.row_id for r in rows if r.topology_quality < 0.25],
        "artifact_alignment_warning": "artifact scores partially missing" if missing else "none",
        "artifact_dominance_proxy": ((sum(art)/len(art)) > 0.5) if art else False,
    }


def build_level_t_omega_event(rows: list[LevelTRealTopologyRow]) -> dict:
    safe = "Local DS003969-style EEG windows were mapped into operational Level T topology telemetry candidates for future M+T residual testing."
    _validate_safe_text(safe)
    return {"dataset_id": "ds003969", "status": "operational_level_t", "n_rows": len(rows), "safe_claim": safe}


def write_level_t_topology_outputs(result: LevelTRealTopologyResult, out_dir: str) -> dict[str, str]:
    base = Path(out_dir); base.mkdir(parents=True, exist_ok=True)
    paths = {
        "features_t.csv": base / "features_t.csv",
        "topology_quality_report.json": base / "topology_quality_report.json",
        "null_placeholder_report.json": base / "null_placeholder_report.json",
        "artifact_alignment_report.json": base / "artifact_alignment_report.json",
        "omega_event.json": base / "omega_event.json",
        "report.md": base / "report.md",
    }
    with paths["features_t.csv"].open("w", encoding="utf-8", newline="") as f:
        writer = None
        for r in result_rows_cache:
            d = asdict(r)
            if writer is None:
                writer = csv.DictWriter(f, fieldnames=list(d.keys())); writer.writeheader()
            writer.writerow(d)
    paths["topology_quality_report.json"].write_text(json.dumps(result.topology_quality_report, indent=2), encoding="utf-8")
    paths["null_placeholder_report.json"].write_text(json.dumps(result.null_placeholder_report, indent=2), encoding="utf-8")
    paths["artifact_alignment_report.json"].write_text(json.dumps(result.artifact_alignment_report, indent=2), encoding="utf-8")
    paths["omega_event.json"].write_text(json.dumps(result.omega_event, indent=2), encoding="utf-8")
    report = "\n".join([
        "# DS003969 Real/Local Level T Topology Extraction",
        "## Dataset/stage",
        "- dataset_id: ds003969",
        "- stage: operational Level T topology telemetry",
        "## Input Level M windows",
        f"- n_rows: {result.n_rows}",
        "## Topology rows",
        f"- n_windows: {result.n_windows}",
        "## Topology quality report",
        f"- {result.topology_quality_report}",
        "## Null placeholder report",
        f"- {result.null_placeholder_report}",
        "## Artifact alignment report",
        f"- {result.artifact_alignment_report}",
        "## Safe claim",
        f"- {result.safe_claim}",
        "## Forbidden claims", *[f"- {x}" for x in result.forbidden_claims],
        "## Warnings", *[f"- {w}" for w in result.warnings],
        "## Next required step",
        "- Run Issue #54 real/local M+T residual benchmark orchestration after Level M and Level T feature tables are available.",
    ])
    _validate_safe_text(report)
    paths["report.md"].write_text(report + "\n", encoding="utf-8")
    return {k: str(v) for k, v in paths.items()}


result_rows_cache: list[LevelTRealTopologyRow] = []
