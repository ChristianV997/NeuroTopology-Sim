from __future__ import annotations

import copy
import dataclasses
import json
import shutil
import socket
from pathlib import Path
from typing import Any, Callable

import pytest

from tools.research_plan_quality.models import ResearchPlan
from tools.research_plan_quality_eval.harness import DEFAULT_MANIFEST
from tools.research_plan_quality_eval.records import PlanRecord, parse_json_bytes

FIXTURE_ROOT: Path = DEFAULT_MANIFEST.parent


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("network access attempted by research-plan evaluation tests")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


@pytest.fixture
def base_plan_dict() -> dict[str, Any]:
    raw = (FIXTURE_ROOT / "plans" / "P01.json").read_bytes()
    return parse_json_bytes(raw, "P01.json")


@pytest.fixture
def plan_from(base_plan_dict: dict[str, Any]) -> Callable[..., ResearchPlan]:
    def _make(**overrides: Any) -> ResearchPlan:
        data = copy.deepcopy(base_plan_dict)
        data.update(overrides)
        return ResearchPlan.from_dict(data)

    return _make


@pytest.fixture
def copy_fixture_tree(tmp_path: Path) -> Callable[[], Path]:
    def _copy() -> Path:
        dest = tmp_path / "fixtures"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(FIXTURE_ROOT, dest)
        return dest / "manifest.json"

    return _copy


def rewrite_json(path: Path, mutate: Callable[[dict[str, Any]], None]) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    mutate(data)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def rehash_labels(manifest_path: Path) -> None:
    import hashlib

    labels = manifest_path.parent / "labels.json"
    digest = hashlib.sha256(labels.read_bytes()).hexdigest()
    rewrite_json(manifest_path, lambda d: d["labels"].update(sha256=digest))


def rehash_plan(manifest_path: Path, fixture_id: str) -> None:
    import hashlib

    def _mutate(data: dict[str, Any]) -> None:
        for record in data["records"]:
            if record["fixture_id"] == fixture_id:
                plan_file = manifest_path.parent / record["plan_file"]
                record["plan_sha256"] = hashlib.sha256(plan_file.read_bytes()).hexdigest()

    rewrite_json(manifest_path, _mutate)


@pytest.fixture
def shipped_records() -> tuple[PlanRecord, ...]:
    from tools.research_plan_quality_eval.manifest import load_manifest, load_plan_records

    return load_plan_records(load_manifest(DEFAULT_MANIFEST))


def record_with(record: PlanRecord, **plan_overrides: Any) -> PlanRecord:
    return dataclasses.replace(record, plan=dataclasses.replace(record.plan, **plan_overrides))
