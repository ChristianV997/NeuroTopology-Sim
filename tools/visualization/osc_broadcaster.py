"""Replay empirical visualization frames as JSONL or optional local OSC."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Iterator

from tools.command_center.real_results_adapter import build_visualization_payload


def frames(root: str | Path | None = None) -> Iterator[dict[str, Any]]:
    payload = build_visualization_payload(root)
    for index, row in enumerate(payload["frames"]):
        yield {
            "schema_version": "neurotemple-frame/v1",
            "frame": index,
            "timestamp": row.get("window_start_s") or float(index),
            "dataset": payload["dataset"],
            "subject_id": row.get("subject_id"),
            "state": row.get("task_label"),
            "q_net_vector": [row.get("q_net") or 0.0, 0.0, 0.0],
            "f_dress_global": row.get("f_dress") or 0.0,
            "active_defects": [],
            "quality": row.get("topology_quality"),
            "spatial_status": payload["spatial_artifact"]["status"],
        }


def write_jsonl(destination: str | Path, root: str | Path | None = None) -> int:
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output.open("w", encoding="utf-8") as handle:
        for frame in frames(root):
            handle.write(json.dumps(frame, sort_keys=True) + "\n")
            count += 1
    return count


def publish_osc(host: str, port: int, hz: float, root: str | Path | None = None) -> int:
    try:
        from pythonosc.udp_client import SimpleUDPClient
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise RuntimeError("Install python-osc to enable live OSC transport") from exc
    client = SimpleUDPClient(host, port)
    interval = 1.0 / max(hz, 1.0)
    count = 0
    for frame in frames(root):
        client.send_message("/neurotopology/frame", json.dumps(frame, separators=(",", ":")))
        count += 1
        time.sleep(interval)
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    parser.add_argument("--jsonl")
    parser.add_argument("--osc", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--hz", type=float, default=20.0)
    args = parser.parse_args(argv)
    if args.osc:
        publish_osc(args.host, args.port, args.hz, args.root)
    elif args.jsonl:
        write_jsonl(args.jsonl, args.root)
    else:
        parser.error("choose --jsonl for deterministic replay or --osc for live local UDP")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
