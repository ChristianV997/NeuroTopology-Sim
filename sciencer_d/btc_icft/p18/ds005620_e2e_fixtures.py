"""P18.1 mock E2E fixture builder for the guarded DS005620 benchmark executor.

Generates a coherent set of in-tree fixture artifacts that match the schemas
the real stage CLIs expect, so that the full P12 -> P13 -> P11 chain can run
end-to-end against deterministic synthetic data — without inferring labels,
fabricating real targets, or downloading anything.

Produced artifacts:
  reviewed_contract.json   — P17.1-shaped p12_external_contract.json
  metadata.csv             — explicit metadata with the contract label column
  signal_blocks/           — minimal canonical signal-block directory
  level_m/features_m_signal.csv  — P9-shaped Level M features (no y)
  level_t/features_t_signal.csv  — P10-shaped Level T topology features

Both binary classes (y=0 and y=1) are available after P12/P13.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

_STRICT_JOIN_KEYS: list[str] = [
    "dataset_id",
    "row_id",
    "source_file",
    "window_id",
    "window_start_s",
    "window_end_s",
    "sample_start",
    "sample_end",
]

_LEVEL_M_FEATURE_COLS: list[str] = _STRICT_JOIN_KEYS + [
    "n_channels",
    "n_samples",
    "sample_rate_hz",
    "spectral_power_proxy",
    "entropy_proxy",
    "lzc_proxy",
    "artifact_score",
    "feature_status",
    "warnings",
]

_LEVEL_T_FEATURE_COLS: list[str] = _STRICT_JOIN_KEYS + [
    "n_channels",
    "n_samples",
    "sample_rate_hz",
    "q_net",
    "q_abs",
    "f_dress",
    "defect_density",
    "n_triangles",
    "n_valid_triangles",
    "topology_quality",
    "topology_status",
    "warnings",
]


@dataclass
class DS005620MockE2EFixturePaths:
    reviewed_contract: str
    metadata: str
    signal_blocks: str
    level_m: str
    level_t: str


def _row_keys(dataset_id: str, idx: int) -> dict[str, str]:
    return {
        "dataset_id": dataset_id,
        "row_id": f"mock__win_{idx}",
        "source_file": "mock_signal_0.csv",
        "window_id": f"win-{idx:03d}",
        "window_start_s": f"{idx * 1.0}",
        "window_end_s": f"{idx * 1.0 + 1.0}",
        "sample_start": f"{idx * 100}",
        "sample_end": f"{idx * 100 + 100}",
    }


def _write_reviewed_contract(path: Path, dataset_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "dataset_id": dataset_id,
        "contract_status": "active_reviewed_external_contract",
        "explicit_label_column": "trial_type",
        "positive_values": ["focus"],
        "negative_values": ["mind_wandering"],
        "label_scope": "window",
        "join_keys": _STRICT_JOIN_KEYS[:],
        "metadata_provenance": "mock_e2e_fixture",
        "activation_provenance": "p17_1_reviewed_materializer",
        "guardrails": [
            "no_label_inference",
            "no_target_fabrication",
            "no_source_contract_modification",
        ],
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _write_metadata(path: Path, dataset_id: str, n_windows: int) -> None:
    """Write a metadata CSV that includes the strict join keys + trial_type.

    Alternates focus/mind_wandering so both classes are present after P12.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = _STRICT_JOIN_KEYS + ["trial_type"]
    rows: list[dict[str, str]] = []
    for i in range(n_windows):
        row = _row_keys(dataset_id, i)
        row["trial_type"] = "focus" if i % 2 == 0 else "mind_wandering"
        rows.append(row)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def _write_signal_blocks(d: Path, dataset_id: str, n_windows: int) -> None:
    d.mkdir(parents=True, exist_ok=True)

    inventory = {
        "dataset_id": dataset_id,
        "n_signal_blocks": 1,
        "signal_blocks": [
            {"block_id": "blk-000", "source_file": "mock_signal_0.csv"},
        ],
    }
    (d / "signal_block_inventory.json").write_text(
        json.dumps(inventory, indent=2), encoding="utf-8"
    )

    inv_cols = _STRICT_JOIN_KEYS + [
        "n_channels", "n_samples", "sample_rate_hz", "extraction_status",
    ]
    with (d / "window_inventory.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=inv_cols)
        w.writeheader()
        for i in range(n_windows):
            row = _row_keys(dataset_id, i)
            row.update({
                "n_channels": "4",
                "n_samples": "100",
                "sample_rate_hz": "100.0",
                "extraction_status": "extracted",
            })
            w.writerow(row)

    (d / "window_signal_values.json").write_text(
        json.dumps({"windows": []}, indent=2), encoding="utf-8"
    )
    (d / "reader_alignment_report.json").write_text(
        json.dumps({
            "dataset_id": dataset_id,
            "ready_for_p9_level_m_signal": True,
            "ready_for_level_m_signal": True,
            "ready_for_p10_level_t_signal": True,
            "ready_for_level_t_signal": True,
            "n_windows": n_windows,
        }, indent=2),
        encoding="utf-8",
    )


def _write_level_m(d: Path, dataset_id: str, n_windows: int) -> None:
    d.mkdir(parents=True, exist_ok=True)
    p = d / "features_m_signal.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_LEVEL_M_FEATURE_COLS)
        w.writeheader()
        for i in range(n_windows):
            row = _row_keys(dataset_id, i)
            row.update({
                "n_channels": "4",
                "n_samples": "100",
                "sample_rate_hz": "100.0",
                "spectral_power_proxy": f"{0.30 + i * 0.05:.4f}",
                "entropy_proxy": f"{0.50 + i * 0.03:.4f}",
                "lzc_proxy": f"{0.40 + i * 0.04:.4f}",
                "artifact_score": f"{0.10 + i * 0.02:.4f}",
                "feature_status": "ok",
                "warnings": "",
            })
            w.writerow(row)


def _write_level_t(d: Path, dataset_id: str, n_windows: int) -> None:
    d.mkdir(parents=True, exist_ok=True)
    p = d / "features_t_signal.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_LEVEL_T_FEATURE_COLS)
        w.writeheader()
        for i in range(n_windows):
            row = _row_keys(dataset_id, i)
            row.update({
                "n_channels": "4",
                "n_samples": "100",
                "sample_rate_hz": "100.0",
                "q_net": f"{0.10 + i * 0.01:.4f}",
                "q_abs": f"{0.20 + i * 0.02:.4f}",
                "f_dress": f"{0.05 + i * 0.01:.4f}",
                "defect_density": f"{0.15 + i * 0.01:.4f}",
                "n_triangles": "4",
                "n_valid_triangles": str(3 + i % 2),
                "topology_quality": f"{0.70 + i * 0.02:.4f}",
                "topology_status": "ok",
                "warnings": "",
            })
            w.writerow(row)


def build_ds005620_mock_e2e_fixtures(
    fixtures_root: str,
    dataset_id: str = "DS005620",
    n_windows: int = 4,
) -> DS005620MockE2EFixturePaths:
    """Materialize a coherent in-tree mock fixture set for the P18.1 E2E run."""
    root = Path(fixtures_root)
    root.mkdir(parents=True, exist_ok=True)

    contract_path = root / "p12_external_contract.json"
    metadata_path = root / "metadata.csv"
    signal_blocks_dir = root / "signal_blocks"
    level_m_dir = root / "level_m"
    level_t_dir = root / "level_t"

    _write_reviewed_contract(contract_path, dataset_id)
    _write_metadata(metadata_path, dataset_id, n_windows)
    _write_signal_blocks(signal_blocks_dir, dataset_id, n_windows)
    _write_level_m(level_m_dir, dataset_id, n_windows)
    _write_level_t(level_t_dir, dataset_id, n_windows)

    return DS005620MockE2EFixturePaths(
        reviewed_contract=str(contract_path),
        metadata=str(metadata_path),
        signal_blocks=str(signal_blocks_dir),
        level_m=str(level_m_dir),
        level_t=str(level_t_dir),
    )
