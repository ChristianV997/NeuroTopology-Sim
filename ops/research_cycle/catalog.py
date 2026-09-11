"""Load and probe the research-cycle operator catalog."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from ops.research_cycle import CATALOG_SCHEMA

DEFAULT_CATALOG = Path(__file__).resolve().parent / "catalog.json"

PLACEHOLDERS = (
    "python",
    "repo_root",
    "output_dir",
    "step_dir",
    "registry",
    "claims",
    "empirical_manifest",
    "provenance",
    "research_state_manifest",
    "performance_pair",
    "candidates",
    "candidate_id",
    "cache_target_root",
    "benchmark_matrix",
    "now",
)


@dataclass(frozen=True)
class StepSpec:
    id: str
    order: int
    title: str
    kind: str
    timeout_s: int
    argv_template: tuple[str, ...] = ()
    builtin: str | None = None
    required_flags: tuple[str, ...] = ()
    availability_probe: Mapping[str, Any] = field(default_factory=dict)
    exit_map: Mapping[str, str] = field(default_factory=dict)
    solver: bool = False
    network: bool = False
    optional: bool = False
    declared_repo_paths_ok: bool = False
    wraps: tuple[str, ...] = ()
    notes: str = ""

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "StepSpec":
        step_id = str(raw.get("id") or "").strip()
        if not step_id:
            raise ValueError("catalog step missing id")
        kind = str(raw.get("kind") or "external")
        argv = tuple(str(part) for part in (raw.get("argv") or raw.get("argv_template") or []))
        probe = raw.get("availability_probe") or {}
        if not isinstance(probe, Mapping):
            probe = {}
        exit_map = raw.get("exit_map") or {}
        if not isinstance(exit_map, Mapping):
            exit_map = {}
        wraps = raw.get("wraps") or []
        return cls(
            id=step_id,
            order=int(raw.get("order") or 0),
            title=str(raw.get("title") or step_id),
            kind=kind,
            timeout_s=int(raw.get("timeout_s") or 60),
            argv_template=argv,
            builtin=str(raw["builtin"]) if raw.get("builtin") else None,
            required_flags=tuple(str(item) for item in (raw.get("required_flags") or [])),
            availability_probe=dict(probe),
            exit_map={str(key): str(value) for key, value in exit_map.items()},
            solver=bool(raw.get("solver")),
            network=bool(raw.get("network")),
            optional=bool(raw.get("optional")),
            declared_repo_paths_ok=bool(raw.get("declared_repo_paths_ok")),
            wraps=tuple(str(item) for item in wraps),
            notes=str(raw.get("notes") or ""),
        )


@dataclass(frozen=True)
class Catalog:
    schema_version: str
    pack_id: str
    steps: tuple[StepSpec, ...]
    optional_steps: tuple[StepSpec, ...]
    path: Path

    def all_steps(self, *, include_optional: bool = False) -> tuple[StepSpec, ...]:
        steps = tuple(sorted(self.steps, key=lambda item: (item.order, item.id)))
        if include_optional:
            extra = tuple(sorted(self.optional_steps, key=lambda item: (item.order, item.id)))
            return steps + extra
        return steps

    def step_by_id(self, step_id: str) -> StepSpec | None:
        for step in (*self.steps, *self.optional_steps):
            if step.id == step_id:
                return step
        return None


def default_catalog_path() -> Path:
    return DEFAULT_CATALOG


def load_catalog(path: Path | None = None) -> Catalog:
    catalog_path = Path(path) if path is not None else default_catalog_path()
    raw = json.loads(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("catalog root must be a JSON object")
    schema = str(raw.get("schema_version") or "")
    if schema != CATALOG_SCHEMA:
        raise ValueError(f"unexpected catalog schema_version {schema!r}; expected {CATALOG_SCHEMA!r}")
    steps = tuple(StepSpec.from_dict(item) for item in (raw.get("steps") or []))
    optional = tuple(StepSpec.from_dict(item) for item in (raw.get("optional_steps") or []))
    if not steps:
        raise ValueError("catalog has no required steps")
    ids = [step.id for step in (*steps, *optional)]
    if len(ids) != len(set(ids)):
        raise ValueError("catalog step ids must be unique")
    return Catalog(
        schema_version=schema,
        pack_id=str(raw.get("pack_id") or "research_cycle_operator_pack"),
        steps=steps,
        optional_steps=optional,
        path=catalog_path,
    )


SequenceLike = tuple[str, ...] | list[str]


def resolve_argv(template: SequenceLike, mapping: Mapping[str, str]) -> list[str]:
    resolved: list[str] = []
    for part in template:
        text = str(part)
        for key, value in mapping.items():
            text = text.replace("{" + key + "}", value)
        resolved.append(text)
    return resolved


def probe_step(step: StepSpec, *, repo_root: Path, python: str) -> tuple[bool, str]:
    probe = dict(step.availability_probe)
    kind = str(probe.get("type") or "").strip()
    if not kind:
        if step.kind == "builtin":
            return True, "builtin"
        if step.argv_template:
            return _probe_argv(step.argv_template, repo_root=repo_root, python=python)
        return False, "no_probe_and_no_argv"
    if kind == "builtin":
        return True, "builtin"
    if kind == "git":
        git = shutil.which("git")
        if git:
            return True, git
        return False, "git_not_on_path"
    if kind == "module":
        module = str(probe.get("module") or "")
        if not module:
            return False, "module_probe_missing_name"
        if importlib.util.find_spec(module) is None:
            return False, f"module_not_importable:{module}"
        return True, module
    if kind == "script":
        rel = str(probe.get("path") or "")
        path = Path(rel)
        if not path.is_absolute():
            path = repo_root / path
        if path.is_file():
            return True, str(path)
        return False, f"script_missing:{path}"
    if kind == "path":
        rel = str(probe.get("path") or "")
        path = Path(rel)
        if not path.is_absolute():
            path = repo_root / path
        if path.exists():
            return True, str(path)
        return False, f"path_missing:{path}"
    if kind == "command":
        name = str(probe.get("command") or "")
        found = shutil.which(name)
        if found:
            return True, found
        return False, f"command_not_on_path:{name}"
    return False, f"unknown_probe_type:{kind}"


def _probe_argv(template: SequenceLike, *, repo_root: Path, python: str) -> tuple[bool, str]:
    if not template:
        return False, "empty_argv"
    first = str(template[0]).replace("{python}", python)
    if first in {python, sys.executable, "python", "python3"} and len(template) >= 3 and str(template[1]) == "-m":
        module = str(template[2])
        if importlib.util.find_spec(module) is None:
            return False, f"module_not_importable:{module}"
        return True, module
    if first in {python, sys.executable, "python", "python3"} and len(template) >= 2:
        script = str(template[1]).replace("{repo_root}", str(repo_root))
        path = Path(script)
        if not path.is_absolute():
            path = repo_root / path
        if path.is_file():
            return True, str(path)
        return False, f"script_missing:{path}"
    found = shutil.which(first)
    if found:
        return True, found
    path = Path(first)
    if not path.is_absolute():
        path = repo_root / path
    if path.is_file():
        return True, str(path)
    return False, f"command_not_available:{first}"
