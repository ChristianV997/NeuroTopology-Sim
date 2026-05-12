"""P18.0 CLI — DS005620 real benchmark readiness gate and dry-run planner.

Inspects reviewed external contract, metadata, canonical signal blocks,
and Level M/T artifact readiness without running any benchmark.

Does NOT run P9/P10/P11.
Does NOT infer labels.
Does NOT fabricate targets.
Does NOT activate contracts.
Does NOT mutate P12 source contracts.

Usage
-----
# Mock-ready (deterministic valid artifacts):
python -m sciencer_d.btc_icft.pipelines.plan_ds005620_real_benchmark \\
  --mock-ready \\
  --out outputs/btc_icft/ds005620_real_benchmark_readiness

# Mock-blocked (deterministic missing/incomplete state):
python -m sciencer_d.btc_icft.pipelines.plan_ds005620_real_benchmark \\
  --mock-blocked \\
  --out outputs/btc_icft/ds005620_real_benchmark_readiness_blocked

# Real/local planning:
python -m sciencer_d.btc_icft.pipelines.plan_ds005620_real_benchmark \\
  --reviewed-contract outputs/btc_icft/ds005620_reviewed_contract/p12_external_contract.json \\
  --metadata data/DS005620/events.tsv \\
  --signal-blocks outputs/btc_icft/eeg_signal_blocks_from_mne/DS005620 \\
  --level-m outputs/btc_icft/eeg_level_m/DS005620 \\
  --level-t outputs/btc_icft/eeg_level_t/DS005620 \\
  --out outputs/btc_icft/ds005620_real_benchmark_readiness
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import tempfile
from pathlib import Path

from sciencer_d.btc_icft.p18.ds005620_benchmark_readiness import (
    _STRICT_JOIN_KEYS,
    build_ds005620_benchmark_readiness,
    write_p18_readiness_outputs,
)

_DEFAULT_OUT = "outputs/btc_icft/ds005620_real_benchmark_readiness"

_DEFAULT_REVIEWED_CONTRACT = (
    "outputs/btc_icft/ds005620_reviewed_contract/p12_external_contract.json"
)
_DEFAULT_METADATA = "data/DS005620/events.tsv"
_DEFAULT_SIGNAL_BLOCKS = "outputs/btc_icft/eeg_signal_blocks_from_mne/DS005620"
_DEFAULT_LEVEL_M = "outputs/btc_icft/eeg_level_m/DS005620"
_DEFAULT_LEVEL_T = "outputs/btc_icft/eeg_level_t/DS005620"


# ---------------------------------------------------------------------------
# Mock artifact builders
# ---------------------------------------------------------------------------

def _write_mock_reviewed_contract(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "dataset_id": "DS005620",
        "contract_status": "active_reviewed_external_contract",
        "explicit_label_column": "trial_type",
        "positive_values": ["focus"],
        "negative_values": ["mind_wandering"],
        "label_scope": "window",
        "join_keys": _STRICT_JOIN_KEYS[:],
        "metadata_provenance": "data/DS005620/events.tsv (local BIDS events sidecar)",
        "activation_provenance": "p17_1_reviewed_materializer",
        "guardrails": [
            "no_label_inference",
            "no_target_fabrication",
            "no_source_contract_modification",
        ],
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _write_mock_metadata(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "onset\tduration\ttrial_type\tsubject_id",
        "0.0\t10.0\tfocus\tsub-01",
        "10.0\t10.0\tmind_wandering\tsub-01",
        "20.0\t10.0\tfocus\tsub-01",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_mock_signal_blocks(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)

    # signal_block_inventory.json
    inventory = {
        "dataset_id": "DS005620",
        "n_signal_blocks": 3,
        "signal_blocks": [
            {"block_id": "blk-000", "source_file": "mock_signal_0.csv"},
        ],
    }
    (d / "signal_block_inventory.json").write_text(
        json.dumps(inventory, indent=2), encoding="utf-8"
    )

    # window_inventory.csv — must include all strict join keys
    cols = _STRICT_JOIN_KEYS + ["n_channels", "n_samples", "sample_rate_hz", "extraction_status"]
    rows = [
        {
            "dataset_id": "DS005620",
            "row_id": f"mock__win_{i}",
            "source_file": "mock_signal_0.csv",
            "window_id": f"win-{i:03d}",
            "window_start_s": str(i * 1.0),
            "window_end_s": str(i * 1.0 + 1.0),
            "sample_start": str(i * 100),
            "sample_end": str(i * 100 + 100),
            "n_channels": "4",
            "n_samples": "100",
            "sample_rate_hz": "100.0",
            "extraction_status": "extracted",
        }
        for i in range(3)
    ]
    with (d / "window_inventory.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)

    # window_signal_values.json
    (d / "window_signal_values.json").write_text(
        json.dumps({"windows": []}, indent=2), encoding="utf-8"
    )

    # reader_alignment_report.json
    ra = {
        "dataset_id": "DS005620",
        "ready_for_p9_level_m_signal": True,
        "ready_for_level_m_signal": True,
        "ready_for_p10_level_t_signal": True,
        "ready_for_level_t_signal": True,
        "n_windows": 3,
    }
    (d / "reader_alignment_report.json").write_text(
        json.dumps(ra, indent=2), encoding="utf-8"
    )


def _write_mock_level_m(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    cols = _STRICT_JOIN_KEYS + [
        "n_channels", "n_samples", "sample_rate_hz",
        "spectral_power_proxy", "entropy_proxy", "lzc_proxy",
        "artifact_score", "feature_status", "warnings",
    ]
    rows = [
        {
            "dataset_id": "DS005620",
            "row_id": f"mock__win_{i}",
            "source_file": "mock_signal_0.csv",
            "window_id": f"win-{i:03d}",
            "window_start_s": str(i * 1.0),
            "window_end_s": str(i * 1.0 + 1.0),
            "sample_start": str(i * 100),
            "sample_end": str(i * 100 + 100),
            "n_channels": "4",
            "n_samples": "100",
            "sample_rate_hz": "100.0",
            "spectral_power_proxy": "0.5",
            "entropy_proxy": "1.2",
            "lzc_proxy": "0.8",
            "artifact_score": "0.0",
            "feature_status": "ok",
            "warnings": "",
        }
        for i in range(3)
    ]
    with (d / "features_m_signal.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)


def _write_mock_level_t(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    cols = _STRICT_JOIN_KEYS + [
        "qz_mean", "qabs_mean", "f_dress_mean",
        "n_plaquettes", "topology_status", "warnings",
    ]
    rows = [
        {
            "dataset_id": "DS005620",
            "row_id": f"mock__win_{i}",
            "source_file": "mock_signal_0.csv",
            "window_id": f"win-{i:03d}",
            "window_start_s": str(i * 1.0),
            "window_end_s": str(i * 1.0 + 1.0),
            "sample_start": str(i * 100),
            "sample_end": str(i * 100 + 100),
            "qz_mean": "0.1",
            "qabs_mean": "0.5",
            "f_dress_mean": "0.0",
            "n_plaquettes": "9",
            "topology_status": "ok",
            "warnings": "",
        }
        for i in range(3)
    ]
    with (d / "features_t_signal.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)


def _build_mock_ready_inputs(tmp_dir: Path) -> dict:
    contract_path = tmp_dir / "p12_external_contract.json"
    metadata_path = tmp_dir / "events.tsv"
    signal_blocks_dir = tmp_dir / "signal_blocks"
    level_m_dir = tmp_dir / "level_m"
    level_t_dir = tmp_dir / "level_t"

    _write_mock_reviewed_contract(contract_path)
    _write_mock_metadata(metadata_path)
    _write_mock_signal_blocks(signal_blocks_dir)
    _write_mock_level_m(level_m_dir)
    _write_mock_level_t(level_t_dir)

    return {
        "reviewed_contract": str(contract_path),
        "metadata": str(metadata_path),
        "signal_blocks": str(signal_blocks_dir),
        "level_m": str(level_m_dir),
        "level_t": str(level_t_dir),
    }


def _build_mock_blocked_inputs() -> dict:
    return {
        "reviewed_contract": "/nonexistent/p12_external_contract.json",
        "metadata": None,
        "signal_blocks": "/nonexistent/signal_blocks",
        "level_m": None,
        "level_t": None,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description=(
            "P18.0: DS005620 real benchmark readiness gate and dry-run planner. "
            "Inspects artifact readiness without running benchmarks or inferring labels."
        )
    )
    p.add_argument(
        "--reviewed-contract",
        default=None,
        dest="reviewed_contract",
        help="Path to P17.1 p12_external_contract.json.",
    )
    p.add_argument(
        "--metadata",
        default=None,
        help="Path to local DS005620 metadata file (events.tsv or equivalent).",
    )
    p.add_argument(
        "--signal-blocks",
        default=None,
        dest="signal_blocks",
        help="Path to canonical signal blocks directory (P19.2 output).",
    )
    p.add_argument(
        "--level-m",
        default=None,
        dest="level_m",
        help="Path to Level M features directory (contains features_m_signal.csv).",
    )
    p.add_argument(
        "--level-t",
        default=None,
        dest="level_t",
        help="Path to Level T features directory (contains features_t_signal.csv).",
    )
    p.add_argument(
        "--out",
        default=_DEFAULT_OUT,
        help="Output directory.",
    )
    p.add_argument(
        "--mock-ready",
        action="store_true",
        default=False,
        help="Use deterministic valid artifact state.",
    )
    p.add_argument(
        "--mock-blocked",
        action="store_true",
        default=False,
        help="Use deterministic missing/incomplete artifact state.",
    )

    a = p.parse_args(argv)

    # Resolve inputs
    _tmp_holder: list = []  # keep tempdir alive
    if a.mock_ready:
        _tmpdir = tempfile.mkdtemp(prefix="p18_mock_ready_")
        _tmp_holder.append(_tmpdir)
        inputs = _build_mock_ready_inputs(Path(_tmpdir))
        print("[p18.0] Using mock-ready artifact state.", file=sys.stderr)
    elif a.mock_blocked:
        inputs = _build_mock_blocked_inputs()
        print("[p18.0] Using mock-blocked artifact state.", file=sys.stderr)
    else:
        inputs = {
            "reviewed_contract": a.reviewed_contract or _DEFAULT_REVIEWED_CONTRACT,
            "metadata": a.metadata or _DEFAULT_METADATA,
            "signal_blocks": a.signal_blocks or _DEFAULT_SIGNAL_BLOCKS,
            "level_m": a.level_m or _DEFAULT_LEVEL_M,
            "level_t": a.level_t or _DEFAULT_LEVEL_T,
        }

    # Build readiness
    result = build_ds005620_benchmark_readiness(inputs)

    # Write outputs
    try:
        paths = write_p18_readiness_outputs(result, a.out)
    except ValueError as exc:
        print(f"[p18.0] FAILED: {exc}", file=sys.stderr)
        return 1

    # Summary
    print("\n[p18.0] DS005620 real benchmark readiness gate complete.", file=sys.stderr)
    print(f"  ready_for_real_benchmark: {result.ready_for_real_benchmark}", file=sys.stderr)
    print(f"  ready_for_p12_alignment: {result.ready_for_p12_alignment}", file=sys.stderr)
    print(f"  ready_for_p13_target_injection: {result.ready_for_p13_target_injection}", file=sys.stderr)
    print(f"  ready_for_p11_target_aware_benchmark: {result.ready_for_p11_target_aware_benchmark}", file=sys.stderr)
    print(f"  execution_blockers: {len(result.execution_blockers)}", file=sys.stderr)
    print(f"  warnings: {len(result.warnings)}", file=sys.stderr)

    if result.execution_blockers:
        print("\n  Blockers:", file=sys.stderr)
        for b in result.execution_blockers:
            print(f"    - {b}", file=sys.stderr)

    print(f"\n  Outputs written to: {a.out}", file=sys.stderr)
    for key, path in paths.items():
        print(f"    {key}: {path}", file=sys.stderr)

    print("\n  Dry-run command plan stages:", file=sys.stderr)
    for cmd in result.dry_run_command_plan:
        ready_str = "ready" if cmd["ready_to_run"] else "blocked"
        blockers_str = ""
        if cmd.get("blockers"):
            blockers_str = f" | BLOCKERS: {cmd['blockers']}"
        print(f"    {cmd['stage']}: {ready_str}{blockers_str}", file=sys.stderr)

    print(
        "\n  NOTE: No benchmarks were run. No labels were inferred. "
        "No targets were fabricated. No contracts were activated.",
        file=sys.stderr,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
