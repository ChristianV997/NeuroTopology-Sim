"""Read-only catalog of current-main vs migration PR worktrees.

Does not modify those trees. Missing roots are recorded as unavailable.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

VARIANT_SPECS: Dict[str, Dict[str, Any]] = {
    "current_main": {
        "pr": None,
        "title": "current origin/main",
        "sha": "ad1d480828b23bf9daf7272d8747302dcca138b7",
        "pr_state": "integrated",
        "default_root_env": "MW_CURRENT_MAIN_ROOT",
        "surfaces": ("chunk_cache", "fetch_plan", "dandi_window", "streaming_manifest"),
    },
    "pr_331": {
        "pr": 331,
        "title": "Approved acquisition adapter",
        "sha": "ee5488e313a2ef5213bec444d9c0f64361f14088",
        "pr_state": "open_draft",
        "default_root_env": "MW_PR_331_ROOT",
        "default_root": "/tmp/mw-pr-331",
        "surfaces": ("approved_adapter", "chunk_cache", "streaming_manifest"),
    },
    "pr_344": {
        "pr": 344,
        "title": "OpenNeuro/BIDS bounded migration",
        "sha": "e9080a9412fac0c5d921741ca9e2f88679084bb6",
        "pr_state": "closed_unmerged",
        "default_root_env": "MW_PR_344_ROOT",
        "default_root": "/tmp/mw-pr-344",
        "surfaces": ("fetch_plan", "chunk_cache", "streaming_manifest"),
    },
    "pr_345": {
        "pr": 345,
        "title": "DANDI/NWB bounded streaming",
        "sha": "59aeb1f45ce7d52245951d60e9a3aeaf04792e64",
        "pr_state": "closed_unmerged",
        "default_root_env": "MW_PR_345_ROOT",
        "default_root": "/tmp/mw-pr-345",
        "surfaces": ("dandi_window", "chunk_cache", "streaming_manifest"),
    },
    "pr_346": {
        "pr": 346,
        "title": "Legacy remote readers to bounded S3",
        "sha": "30cbf8dd1040f6b3352657bd51daba20dba2dfa4",
        "pr_state": "open_draft",
        "default_root_env": "MW_PR_346_ROOT",
        "default_root": "/tmp/mw-pr-346",
        "surfaces": ("bounded_s3", "chunk_cache", "streaming_manifest"),
    },
}

_MARKERS = {
    "chunk_cache": "tools/data_access/chunk_cache/cache_engine.py",
    "approved_adapter": "tools/data_access/approved_adapter/adapter.py",
    "fetch_ds000245": "tools/fetch_ds000245.py",
    "dandi_nwb": "data/dandi_nwb_ingest.py",
    "s3_fetchers": "validation/s3_fetchers.py",
    "streaming_manifest": "tools/streaming/base_runner.py",
}


def resolve_variant_root(name: str, *, harness_root: str | Path, overrides: Optional[Dict[str, str]] = None) -> Optional[Path]:
    spec = VARIANT_SPECS[name]
    overrides = overrides or {}
    if name in overrides and overrides[name]:
        return Path(overrides[name]).resolve()
    env_key = spec.get("default_root_env")
    if env_key and os.environ.get(env_key):
        return Path(os.environ[env_key]).resolve()
    if name == "current_main":
        return Path(harness_root).resolve()
    default = spec.get("default_root")
    if default and Path(default).is_dir():
        return Path(default).resolve()
    return None


def detect_capabilities(root: Path) -> Dict[str, Any]:
    files = {key: (root / rel).is_file() for key, rel in _MARKERS.items()}
    fetch_plan = False
    window_request = False
    bounded_s3 = False
    if files["fetch_ds000245"]:
        text = (root / _MARKERS["fetch_ds000245"]).read_text(encoding="utf-8", errors="replace")
        fetch_plan = "def plan(" in text and "class BoundedObjectRequest" in text
    if files["dandi_nwb"]:
        text = (root / _MARKERS["dandi_nwb"]).read_text(encoding="utf-8", errors="replace")
        window_request = "class WindowRequest" in text and "def read_bounded_window" in text
    if files["s3_fetchers"]:
        text = (root / _MARKERS["s3_fetchers"]).read_text(encoding="utf-8", errors="replace")
        bounded_s3 = "class BoundedS3ObjectStore" in text
    return {
        "files": files,
        "chunk_cache": files["chunk_cache"],
        "approved_adapter": files["approved_adapter"],
        "fetch_plan": fetch_plan,
        "dandi_window": window_request,
        "bounded_s3": bounded_s3,
        "streaming_manifest": files["streaming_manifest"],
        "runnable": any(
            (files["chunk_cache"], files["approved_adapter"], fetch_plan, window_request, bounded_s3, files["streaming_manifest"])
        ),
    }


def inventory_variants(harness_root: str | Path, *, overrides: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for name, spec in VARIANT_SPECS.items():
        root = resolve_variant_root(name, harness_root=harness_root, overrides=overrides)
        caps = detect_capabilities(root) if root is not None and root.is_dir() else None
        rows.append(
            {
                "variant": name,
                "pr": spec["pr"],
                "title": spec["title"],
                "sha": spec["sha"],
                "pr_state": spec["pr_state"],
                "root": str(root) if root is not None else None,
                "available": bool(root is not None and root.is_dir()),
                "capabilities": caps,
                "inspected_read_only": True,
            }
        )
    return rows
