"""ds005620 (propofol sedation) Level M window scaffold.

The shared Level-M row/result dataclasses, metric helpers, contrast-evaluation,
and output-writing that this module used to duplicate now live in ONE place
(`generic_windows.py`) and are driven by this dataset's registry config. Public
names are preserved and output is byte-identical (proven in
tests/btc_icft/test_onboarding_registry.py).

The legacy BIDS-inspection / mock-fixture helpers below
(`load_bids_inspection_outputs`, `build_level_m_windows_from_bids_inventory`,
`build_mock_level_m_windows_from_inspection`, `extract_level_m_window_features`)
are ds005620-specific (they predate the real-signal streaming path) and stay
here -- they are not part of the generic real-signal pipeline.
"""
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from sciencer_d.btc_icft.datasets.onboarding_registry import get_dataset_config
from sciencer_d.btc_icft.level_m.features import extract_level_m_features
from sciencer_d.btc_icft.level_m.generic_windows import (  # noqa: F401  (re-exported public API)
    LevelMRealWindowResult,
    LevelMWindowRow,
    build_window_artifact_report,
    build_window_leakage_report,
)
from sciencer_d.btc_icft.level_m import generic_windows as _G

_CONFIG = get_dataset_config("ds005620")


def evaluate_level_m_windows(rows: list[LevelMWindowRow], task: str) -> LevelMRealWindowResult:
    return _G.evaluate_level_m_windows(rows, _CONFIG, task=task)


def write_level_m_window_outputs(result: LevelMRealWindowResult, out_dir: str) -> dict[str, str]:
    return _G.write_level_m_window_outputs(result, out_dir, _CONFIG)


# ── Legacy ds005620-specific BIDS-inspection / mock-fixture helpers ───────────
# (predate the real-signal streaming path; kept for ds005620's own baseline tests)

def load_bids_inspection_outputs(inspection_dir: str) -> dict:
    base = Path(inspection_dir)
    required = ["file_inventory.json", "label_candidates.json", "contract_report.json", "report.md"]
    missing = [name for name in required if not (base / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing required BIDS inspection outputs in {inspection_dir}: {missing}. "
            "Run inspect_ds005620_bids first to generate file_inventory.json, label_candidates.json, contract_report.json, and report.md."
        )
    return {
        "file_inventory": json.loads((base / "file_inventory.json").read_text(encoding="utf-8")),
        "label_candidates": json.loads((base / "label_candidates.json").read_text(encoding="utf-8")),
        "contract_report": json.loads((base / "contract_report.json").read_text(encoding="utf-8")),
        "report_md": (base / "report.md").read_text(encoding="utf-8"),
        "inspection_dir": str(base),
    }


def _pick_label(match: dict | None, key: str, warnings: list[str]) -> str | None:
    if not match:
        warnings.append("missing label candidate row; labels left unknown")
        return None
    value = match.get(key)
    if value is None:
        warnings.append(f"missing {key} in label candidate")
    return value


def build_level_m_windows_from_bids_inventory(inspection: dict, window_seconds: float = 10.0, max_windows_per_file: int = 2) -> list[LevelMWindowRow]:
    inventory = inspection.get("file_inventory", {})
    labels = inspection.get("label_candidates", [])
    by_source = {x.get("source") or x.get("relative_path"): x for x in labels if isinstance(x, dict)}
    rows: list[LevelMWindowRow] = []
    eeg_candidates = inventory.get("eeg_candidates", [])

    for rec in eeg_candidates:
        if not rec.get("is_eeg_candidate", True):
            continue
        source_file = rec.get("path") or rec.get("relative_path") or "unknown"
        rel = rec.get("relative_path")
        subject = rec.get("subject_id") or "unknown_subject"
        session = rec.get("session_id")
        run = rec.get("run_id")
        task = rec.get("task_label")
        match = by_source.get(rel)

        for idx in range(max_windows_per_file):
            warns: list[str] = []
            state = _pick_label(match, "state_label", warns)
            behavior = _pick_label(match, "behavior_label", warns)
            report = _pick_label(match, "report_label", warns)
            task_label = _pick_label(match, "task_label", warns) or task

            row_id = f"{subject}_{session or 'noses'}_{run or 'norun'}_{task_label or 'unknown'}_win-{idx}"
            rows.append(LevelMWindowRow(
                row_id=row_id,
                subject_id=subject,
                session_id=session,
                run_id=run,
                window_id=f"win-{idx}",
                task_label=task_label,
                state_label=state,
                behavior_label=behavior,
                report_label=report,
                y=None,
                spectral_power_proxy=None,
                entropy_proxy=None,
                lzc_proxy=None,
                artifact_score=None,
                source_file=source_file,
                window_start_s=idx * window_seconds,
                window_end_s=(idx + 1) * window_seconds,
                warnings=warns,
            ))
    return rows


def build_mock_level_m_windows_from_inspection() -> list[LevelMWindowRow]:
    return [
        LevelMWindowRow("sub-01_ses-01_run-01_awake_win-0", "sub-01", "ses-01", "01", "win-0", "awake", "awake", "responsive", "experience", None, None, None, None, None, "mock/sub-01_task-awake_run-01_eeg.edf", 0.0, 10.0, []),
        LevelMWindowRow("sub-01_ses-01_run-01_sedated_win-1", "sub-01", "ses-01", "01", "win-1", "sedated", "sedated", "unresponsive", "experience", None, None, None, None, None, "mock/sub-01_task-sedated_run-01_eeg.edf", 10.0, 20.0, []),
        LevelMWindowRow("sub-02_ses-01_run-01_awake_win-0", "sub-02", "ses-01", "01", "win-0", "awake", "awake", "responsive", "no_experience", None, None, None, None, None, "mock/sub-02_task-awake_run-01_eeg.edf", 0.0, 10.0, []),
        LevelMWindowRow("sub-02_ses-01_run-01_sedated_win-1", "sub-02", "ses-01", "01", "win-1", "sedated", "sedated", "unresponsive", "no_experience", None, None, None, None, None, "mock/sub-02_task-sedated_run-01_eeg.edf", 10.0, 20.0, []),
    ]


def _signal_from_seed(seed: str) -> list[float]:
    base = max(1, sum(ord(ch) for ch in seed) % 91)
    return [((base + i * 7) % 97) / 100.0 for i in range(64)]


def extract_level_m_window_features(windows: list[LevelMWindowRow]) -> list[LevelMWindowRow]:
    out: list[LevelMWindowRow] = []
    for row in windows:
        signal = _signal_from_seed(f"{row.source_file}:{row.row_id}")
        feats = extract_level_m_features(signal)
        warns = list(row.warnings)
        warns.append("fixture-derived Level M features; not real EEG signal extraction")
        out.append(LevelMWindowRow(**{**asdict(row), **feats, "warnings": warns}))
    return out
