"""P18.1 CLI — DS005620 guarded real benchmark executor.

Default mode is dry-run. Real execution requires both --execute and
--peer-reviewed-contract-confirmed. Mock E2E mode (--mock-e2e) materializes
a coherent in-tree fixture set and runs the real P12 -> P13 -> P11 CLIs
against it.

Usage
-----
# Dry-run plan against default paths (writes artifacts, runs nothing):
python -m sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark \\
  --out outputs/btc_icft/ds005620_real_benchmark_execution

# Mock E2E run (one command, end-to-end):
python -m sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark \\
  --mock-e2e --execute --peer-reviewed-contract-confirmed \\
  --out outputs/btc_icft/ds005620_real_benchmark_execution_mock

# Real/local run (requires peer review confirmation):
python -m sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark \\
  --reviewed-contract outputs/btc_icft/ds005620_reviewed_contract/p12_external_contract.json \\
  --metadata data/DS005620/events.tsv \\
  --signal-blocks outputs/btc_icft/eeg_signal_blocks_from_mne/DS005620 \\
  --level-m outputs/btc_icft/eeg_level_m/DS005620 \\
  --level-t outputs/btc_icft/eeg_level_t/DS005620 \\
  --execute --peer-reviewed-contract-confirmed \\
  --out outputs/btc_icft/ds005620_real_benchmark_execution
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sciencer_d.btc_icft.p18.ds005620_e2e_fixtures import (
    build_ds005620_mock_e2e_fixtures,
)
from sciencer_d.btc_icft.p18.ds005620_real_benchmark_executor import (
    build_execution_paths,
    run_ds005620_real_benchmark_execution,
    write_ds005620_real_benchmark_outputs,
)

_DEFAULT_OUT = "outputs/btc_icft/ds005620_real_benchmark_execution"

_DEFAULTS = {
    "reviewed_contract": "outputs/btc_icft/ds005620_reviewed_contract/p12_external_contract.json",
    "metadata": "data/DS005620/events.tsv",
    "signal_blocks": "outputs/btc_icft/eeg_signal_blocks_from_mne/DS005620",
    "level_m": "outputs/btc_icft/eeg_level_m/DS005620",
    "level_t": "outputs/btc_icft/eeg_level_t/DS005620",
    "p12_out": "outputs/btc_icft/eeg_labels/DS005620_reviewed",
    "p13_out": "outputs/btc_icft/eeg_targets/DS005620_reviewed",
    "p11_out": "outputs/btc_icft/eeg_signal_mt/DS005620_reviewed",
}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description=(
            "P18.1: DS005620 guarded real benchmark executor. "
            "Orchestrates P12 -> P13 -> P11 only when prerequisites exist "
            "and only when peer review is explicitly confirmed."
        )
    )
    p.add_argument("--dataset-id", default="DS005620")
    p.add_argument("--out", default=_DEFAULT_OUT)
    p.add_argument("--reviewed-contract", default=None, dest="reviewed_contract")
    p.add_argument("--metadata", default=None)
    p.add_argument("--signal-blocks", default=None, dest="signal_blocks")
    p.add_argument("--level-m", default=None, dest="level_m")
    p.add_argument("--level-t", default=None, dest="level_t")
    p.add_argument("--p12-out", default=None, dest="p12_out")
    p.add_argument("--p13-out", default=None, dest="p13_out")
    p.add_argument("--p11-out", default=None, dest="p11_out")
    p.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Actually run P12/P13/P11. Requires --peer-reviewed-contract-confirmed.",
    )
    p.add_argument(
        "--peer-reviewed-contract-confirmed",
        action="store_true",
        default=False,
        dest="peer_reviewed_contract_confirmed",
        help="Confirm that a human peer has reviewed the reviewed external contract.",
    )
    p.add_argument(
        "--mock-e2e",
        action="store_true",
        default=False,
        dest="mock_e2e",
        help="Materialize in-tree mock fixtures and run the full chain against them.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        dest="dry_run_flag",
        help="Force dry-run (implied when --execute is omitted).",
    )
    p.add_argument(
        "--stop-after",
        default=None,
        dest="stop_after",
        choices=["p12", "p13", "p11"],
        help="Run up to and including this stage; later stages are marked skipped.",
    )
    p.add_argument(
        "--continue-on-stage-failure",
        action="store_true",
        default=False,
        dest="continue_on_stage_failure",
        help="Continue to the next stage even if the prior stage failed.",
    )

    a = p.parse_args(argv)

    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if a.mock_e2e:
        fixtures_root = out_dir / "_fixtures"
        fx = build_ds005620_mock_e2e_fixtures(str(fixtures_root), a.dataset_id)
        reviewed_contract = fx.reviewed_contract
        metadata = fx.metadata
        signal_blocks = fx.signal_blocks
        level_m = fx.level_m
        level_t = fx.level_t
    else:
        reviewed_contract = a.reviewed_contract or _DEFAULTS["reviewed_contract"]
        metadata = a.metadata or _DEFAULTS["metadata"]
        signal_blocks = a.signal_blocks or _DEFAULTS["signal_blocks"]
        level_m = a.level_m or _DEFAULTS["level_m"]
        level_t = a.level_t or _DEFAULTS["level_t"]

    p12_out = a.p12_out or _DEFAULTS["p12_out"]
    p13_out = a.p13_out or _DEFAULTS["p13_out"]
    p11_out = a.p11_out or _DEFAULTS["p11_out"]
    if a.mock_e2e:
        # Keep mock outputs inside the artifact root to avoid contaminating
        # outputs/btc_icft default paths.
        p12_out = str(out_dir / "stage_outputs" / "p12_eeg_labels")
        p13_out = str(out_dir / "stage_outputs" / "p13_eeg_targets")
        p11_out = str(out_dir / "stage_outputs" / "p11_signal_mt")

    paths = build_execution_paths(
        artifact_root=str(out_dir),
        reviewed_contract=reviewed_contract,
        metadata=metadata,
        signal_blocks=signal_blocks,
        level_m=level_m,
        level_t=level_t,
        p12_out=p12_out,
        p13_out=p13_out,
        p11_out=p11_out,
    )

    execute = a.execute and not a.dry_run_flag

    result = run_ds005620_real_benchmark_execution(
        paths,
        dataset_id=a.dataset_id,
        execute=execute,
        peer_reviewed_contract_confirmed=a.peer_reviewed_contract_confirmed,
        mock_e2e=a.mock_e2e,
        stop_after=a.stop_after,
        continue_on_stage_failure=a.continue_on_stage_failure,
    )

    try:
        out_paths = write_ds005620_real_benchmark_outputs(result, str(out_dir))
    except ValueError as exc:
        print(f"[p18.1] FAILED: {exc}", file=sys.stderr)
        return 1

    print(f"\n[p18.1] DS005620 benchmark execution complete.", file=sys.stderr)
    print(f"  mode: {result.mode}", file=sys.stderr)
    print(f"  dry_run: {result.dry_run}", file=sys.stderr)
    print(
        f"  peer_reviewed_contract_confirmed: "
        f"{result.peer_reviewed_contract_confirmed}",
        file=sys.stderr,
    )
    print(
        f"  P12: executed={result.p12_executed} succeeded={result.p12_succeeded}",
        file=sys.stderr,
    )
    print(
        f"  P13: executed={result.p13_executed} succeeded={result.p13_succeeded}",
        file=sys.stderr,
    )
    print(
        f"  P11: executed={result.p11_executed} succeeded={result.p11_succeeded}",
        file=sys.stderr,
    )
    print(f"  benchmark_completed: {result.benchmark_completed}", file=sys.stderr)

    if result.execution_blockers:
        print("\n  Execution blockers:", file=sys.stderr)
        for b in result.execution_blockers:
            print(f"    - {b}", file=sys.stderr)

    print(f"\n  Outputs written to: {out_dir}", file=sys.stderr)
    for key, path in out_paths.items():
        print(f"    {key}: {path}", file=sys.stderr)

    if a.execute and not a.peer_reviewed_contract_confirmed and result.execution_blockers:
        return 2
    if not result.dry_run and not result.benchmark_completed:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
