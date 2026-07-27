"""Create an auditable EC2 batch job plan without launching instances.

Submission is intentionally outside this helper: it emits a JSON job matrix
that can be reviewed and handed to AWS Batch, ParallelCluster, or an operator.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def build_job_plan(*, shards: int, seed: int, output_dir: Path, timeout_s: int, max_workers: int) -> dict[str, Any]:
    if shards < 1 or max_workers < 1 or timeout_s < 1:
        raise ValueError("shards, timeout, and workers must be positive")
    jobs = []
    for index in range(shards):
        jobs.append({
            "job_name": f"sciencerd-discovery-{index:03d}",
            "shard_index": index,
            "shard_count": shards,
            "command": ["python", "scripts/run_campaign.py", "--lane", "discovery",
                         "--execution-mode", "ec2_batch", "--seed", str(seed),
                         "--shard-index", str(index), "--shard-count", str(shards),
                         "--max-workers", str(max_workers), "--timeout-s", str(timeout_s),
                         "--output-dir", str(output_dir / f"shard-{index:03d}")],
            "braket_submission": False,
            "cost_control": {"spot_allowed": True, "qpu_allowed": False, "max_runtime_s": timeout_s},
        })
    return {"schema": "ScienceR-Dsim.EC2CampaignJobPlan.v1", "execution": "plan_only",
            "scientific_status": "LOCAL_REFERENCE_ONLY", "jobs": jobs}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shards", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20260726)
    parser.add_argument("--timeout-s", type=int, default=1800)
    parser.add_argument("--max-workers", type=int, default=2)
    parser.add_argument("--output", type=Path, default=Path("artifacts/campaign/ec2_job_plan.json"))
    args = parser.parse_args()
    payload = build_job_plan(shards=args.shards, seed=args.seed, output_dir=Path("artifacts/campaign"),
                             timeout_s=args.timeout_s, max_workers=args.max_workers)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "jobs": len(payload["jobs"]), "submitted": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
