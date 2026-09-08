#!/usr/bin/env python
"""Run a bounded benchmark matrix, one configuration per isolated child process.

This script is both the **parent orchestrator** and the **child workload** (via
the ``child`` subcommand), so it is fully self-contained and imports no
streaming/kernel/benchmark code:

* ``child``  -- runs one deterministic synthetic workload and prints a telemetry
  JSON object (checksum, tracemalloc peak, peak RSS via ``resource``). Supports
  fault-injection flags for testing (``--inject-sleep``, ``--inject-crash``,
  ``--inject-invalid-json``, ``--inject-omit-rss``).
* (default) -- builds a bounded matrix of configurations and runs each in its own
  child process through :mod:`tools.streaming.process_runner`, then writes an
  atomic JSON report and prints a summary.

Scientific-integrity note: fixtures are synthetic and deterministic and are
performance evidence only -- never scientific evidence. A timeout or crash is an
operational outcome, not a result.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# When this file is launched by absolute path, Python puts only ``scripts/``
# on ``sys.path``. Make the standalone child entrypoint importable without
# requiring callers to set PYTHONPATH.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.streaming.process_runner import (
    Outcome,
    build_python_command,
    run_matrix,
)


# --------------------------------------------------------------------------- #
# Child workload
# --------------------------------------------------------------------------- #
def _child_workload(config: Dict[str, Any]) -> Dict[str, Any]:
    import tracemalloc

    import numpy as np

    samples = int(config.get("samples", 10000))
    channels = int(config.get("channels", 8))
    seed = int(config.get("seed", 0))

    tracemalloc.start()
    tracemalloc.reset_peak()
    rng = np.random.default_rng(seed)
    block = rng.standard_normal((samples, channels)).astype(np.float64)
    checksum = float(block.sum())
    _, tm_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    peak_rss = None
    try:
        import resource

        ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak_rss = int(ru) if sys.platform == "darwin" else int(ru) * 1024
    except Exception:
        peak_rss = None

    return {
        "checksum": checksum,
        "tracemalloc_peak_bytes": int(tm_peak),
        "peak_rss_bytes": peak_rss,
        "correctness_ok": True,
        "synthetic": True,
        "config": config,
    }


def _child_main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(prog="child")
    ap.add_argument("--config-json", required=True)
    ap.add_argument("--inject-sleep", type=float, default=0.0)
    ap.add_argument("--inject-crash", action="store_true")
    ap.add_argument("--inject-invalid-json", action="store_true")
    ap.add_argument("--inject-omit-rss", action="store_true")
    args = ap.parse_args(argv)

    config = json.loads(args.config_json)

    if args.inject_sleep > 0:
        time.sleep(args.inject_sleep)
    if args.inject_crash:
        sys.stderr.write("injected crash\n")
        return 7
    if args.inject_invalid_json:
        sys.stdout.write("this is not json\n")
        return 0

    telemetry = _child_workload(config)
    if args.inject_omit_rss:
        telemetry["peak_rss_bytes"] = None
    # Finite JSON only (no NaN/Infinity).
    sys.stdout.write(json.dumps(telemetry, allow_nan=False))
    sys.stdout.write("\n")
    return 0


# --------------------------------------------------------------------------- #
# Parent orchestrator
# --------------------------------------------------------------------------- #
def build_matrix(samples_list: List[int], channels_list: List[int], seed: int) -> List[Dict[str, Any]]:
    configs: List[Dict[str, Any]] = []
    for samples in samples_list:
        for channels in channels_list:
            configs.append({"samples": samples, "channels": channels, "seed": seed})
    return configs


def make_command_builder(script_path: str):
    def _builder(config: Dict[str, Any]):
        return build_python_command(
            script_path,
            ["child", "--config-json", json.dumps(config, allow_nan=False)],
        )
    return _builder


def main(argv: List[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "child":
        return _child_main(argv[1:])

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--samples-list", type=int, nargs="+", default=[20000, 80000])
    ap.add_argument("--channels-list", type=int, nargs="+", default=[8, 32])
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--timeout-s", type=float, default=60.0)
    ap.add_argument("--max-workers", type=int, default=1)
    ap.add_argument("--sequential", action="store_true")
    ap.add_argument("--output", default=None, help="atomic JSON report path")
    ap.add_argument("--json", action="store_true", help="print full report JSON")
    args = ap.parse_args(argv)

    configs = build_matrix(args.samples_list, args.channels_list, args.seed)
    report = run_matrix(
        make_command_builder(__file__),
        configs,
        timeout_s=args.timeout_s,
        max_workers=args.max_workers,
        sequential=args.sequential,
        required_metrics=("checksum",),
        output_path=args.output,
    )

    if args.json:
        print(json.dumps(report, indent=2, allow_nan=False))
    else:
        print(f"platform={report['runner']['platform']} "
              f"workers={report['runner']['max_workers']} "
              f"psutil={report['runner']['psutil_available']} "
              f"configs={report['num_configs']}")
        print(f"summary={report['summary']} all_passed={report['all_passed']}")
        for res in report["results"]:
            cfg = res["config"]
            rss = res["peak_rss_bytes"]
            sampled = res["parent_sampled_peak_rss_bytes"]
            rss_s = "n/a" if rss is None else f"{rss/1e6:.1f}MB"
            sampled_s = "n/a" if sampled is None else f"{sampled/1e6:.1f}MB"
            print(f"  {res['outcome']:22s} cfg={cfg} elapsed={res['elapsed_s']*1e3:.1f}ms "
                  f"tm_peak={res['tracemalloc_peak_bytes']} child_rss={rss_s} sampled_rss={sampled_s}")
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
