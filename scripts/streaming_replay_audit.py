#!/usr/bin/env python
"""CLI: replay audit for checkpointed bounded streaming.

Compares a clean run, an interrupted/resumed run, and (when overlap=0) the
unmodified ``bounded_stream`` reference. Emits finite JSON only.

Usage
-----
    PYTHONPATH=. python scripts/streaming_replay_audit.py \\
        --samples 8000 --channels 6 --chunk-size 256 --interrupt-after 5 \\
        --work-dir /tmp/streaming_replay_audit --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tools.streaming.memory_telemetry import dumps as telemetry_dumps
from tools.streaming.replay import build_replay_audit, make_fixture


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--samples", type=int, default=8000)
    p.add_argument("--channels", type=int, default=6)
    p.add_argument("--chunk-size", type=int, default=256)
    p.add_argument("--overlap", type=int, default=0)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--interrupt-after", type=int, default=5,
                   help="Windows to process before cooperative interrupt")
    p.add_argument("--work-dir", type=str, default="artifacts/streaming_replay_audit")
    p.add_argument("--no-memory", action="store_true",
                   help="Disable tracemalloc peak capture")
    p.add_argument("--no-bounded-reference", action="store_true",
                   help="Skip comparison against tools.streaming.bounded.bounded_stream")
    p.add_argument("--json", action="store_true", help="Print JSON to stdout")
    p.add_argument("--out", type=str, default=None,
                   help="Optional path to write the audit JSON file")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.samples < 1 or args.channels < 1 or args.chunk_size < 1:
        print("samples, channels, and chunk-size must be >= 1", file=sys.stderr)
        return 2
    if args.interrupt_after < 1:
        print("interrupt-after must be >= 1", file=sys.stderr)
        return 2

    signal = make_fixture(args.samples, args.channels, seed=args.seed)
    report = build_replay_audit(
        signal,
        args.chunk_size,
        args.work_dir,
        interrupt_after_windows=args.interrupt_after,
        overlap=args.overlap,
        track_memory=not args.no_memory,
        compare_bounded_reference=not args.no_bounded_reference,
    )
    payload = report.to_dict()

    out_path = Path(args.out) if args.out else Path(args.work_dir) / "replay_audit.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Prefer memory_telemetry.dumps for finite JSON when available.
    text = telemetry_dumps(payload, indent=2)
    out_path.write_text(text + ("\n" if not text.endswith("\n") else ""), encoding="utf-8")

    if args.json:
        print(text)
    else:
        eq = payload["equivalence"]
        print("streaming replay audit")
        print(f"  source_checksum={payload['source_checksum'][:16]}...")
        print(f"  schema={payload['checkpoint_schema_version']}")
        print(f"  clean_vs_resumed={eq['clean_vs_resumed']}")
        print(f"  clean_vs_bounded_reference={eq['clean_vs_bounded_reference']}")
        print(f"  checksum_clean={eq['checksum_clean']}")
        print(f"  checksum_resumed={eq['checksum_resumed']}")
        mem = payload["memory_metadata"]
        print(f"  clean_peak_bytes={mem['clean_peak_bytes']}")
        print(f"  resumed_peak_bytes={mem['resumed_peak_bytes']}")
        print(f"  wrote {out_path}")

    if not payload["equivalence"]["clean_vs_resumed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
