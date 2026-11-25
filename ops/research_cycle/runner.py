"""Shared orchestration for the research-cycle operator pack."""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ops.research_cycle.catalog import Catalog, StepSpec, probe_step, resolve_argv
from ops.research_cycle.exit_codes import aggregate_statuses, normalize_status, status_to_exit
from ops.research_cycle.json_util import dumps, json_safe, load_finite_json, shared_json_helper_available, text_has_nonfinite_tokens
from ops.research_cycle.reporting import build_report, write_report_files
from ops.research_cycle.safety import SafetyError, assert_write_path, assert_allowed_command, sanitize_env
from ops.research_cycle.surfaces import emit_surfaces

DEFAULT_CACHE_TARGET = "outputs/research_cycle_operator_pack/declared_target"
DEFAULT_NOW = "2026-09-10T00:00:00+00:00"
DEFAULT_FIXTURE_ROOT = Path("tests/ops/research_cycle/fixtures")


@dataclass
class RunConfig:
    repo_root: Path
    output_dir: Path
    catalog: Catalog
    python: str
    allow_solver: bool = False
    include_optional: bool = False
    step_ids: tuple[str, ...] | None = None
    generated_at: str | None = DEFAULT_NOW
    shell_family: str = "posix"
    registry: Path | None = None
    claims: Path | None = None
    empirical_manifest: Path | None = None
    provenance: Path | None = None
    research_state_manifest: Path | None = None
    performance_pair: Path | None = None
    candidates: Path | None = None
    candidate_id: str = "2363a3d50984c392"
    cache_target_root: str = DEFAULT_CACHE_TARGET
    benchmark_matrix: Path | None = None
    timeout_override: int | None = None
    emit_surfaces_enabled: bool = True


@dataclass
class StepResult:
    spec: StepSpec
    status: str
    exit_code: int | None
    argv: list[str] = field(default_factory=list)
    reason: str | None = None
    stdout: str = ""
    stderr: str = ""
    duration_s: float | None = None
    note: str | None = None
    probe_detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return json_safe(
            {
                "id": self.spec.id,
                "order": self.spec.order,
                "title": self.spec.title,
                "kind": self.spec.kind,
                "status": self.status,
                "exit_code": self.exit_code,
                "timeout_s": self.spec.timeout_s,
                "argv": list(self.argv),
                "wraps": list(self.spec.wraps),
                "reason": self.reason,
                "note": self.note,
                "probe_detail": self.probe_detail,
                "duration_s": self.duration_s,
                "optional": self.spec.optional,
                "solver": self.spec.solver,
            }
        )


def discover_repo_root(start: Path | None = None) -> Path:
    here = Path(start or Path(__file__).resolve()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / ".git").exists() and (candidate / "scripts").is_dir():
            return candidate
        if (candidate / "ops" / "research_cycle" / "catalog.json").is_file() and (candidate / "scripts").is_dir():
            return candidate
    return Path(__file__).resolve().parents[2]


def fixture_path(repo_root: Path, *parts: str) -> Path:
    return repo_root / DEFAULT_FIXTURE_ROOT.joinpath(*parts)


def apply_fixture_defaults(config: RunConfig) -> RunConfig:
    root = config.repo_root
    if config.registry is None:
        config.registry = fixture_path(root, "registry.json")
    if config.claims is None:
        config.claims = fixture_path(root, "claims.json")
    if config.empirical_manifest is None:
        config.empirical_manifest = fixture_path(root, "empirical_manifest.json")
    if config.provenance is None:
        config.provenance = fixture_path(root, "provenance.json")
    if config.research_state_manifest is None:
        config.research_state_manifest = fixture_path(root, "research_state", "manifest.json")
    if config.performance_pair is None:
        config.performance_pair = fixture_path(root, "performance_pair.json")
    if config.candidates is None:
        config.candidates = fixture_path(root, "dataset_candidates.json")
    if config.benchmark_matrix is None:
        smoke = root / "tools" / "benchmark_orchestration" / "examples" / "local_smoke_matrix.json"
        fixture_matrix = fixture_path(root, "benchmark_matrix.json")
        config.benchmark_matrix = fixture_matrix if fixture_matrix.is_file() else smoke
    return config


def selected_steps(config: RunConfig) -> list[StepSpec]:
    steps = list(config.catalog.all_steps(include_optional=config.include_optional))
    if config.step_ids:
        wanted = {item.strip() for item in config.step_ids if item.strip()}
        chosen = [step for step in steps if step.id in wanted]
        missing = wanted - {step.id for step in chosen}
        if missing:
            raise SafetyError(f"unknown step id(s): {sorted(missing)}")
        return chosen
    return [step for step in steps if not step.optional or config.include_optional]


def mapping_for(config: RunConfig, step: StepSpec) -> dict[str, str]:
    step_dir = config.output_dir / "steps" / step.id
    step_dir.mkdir(parents=True, exist_ok=True)
    return {
        "python": config.python,
        "repo_root": str(config.repo_root),
        "output_dir": str(config.output_dir),
        "step_dir": str(step_dir),
        "registry": str(config.registry or ""),
        "claims": str(config.claims or ""),
        "empirical_manifest": str(config.empirical_manifest or ""),
        "provenance": str(config.provenance or ""),
        "research_state_manifest": str(config.research_state_manifest or ""),
        "performance_pair": str(config.performance_pair or ""),
        "candidates": str(config.candidates or ""),
        "candidate_id": config.candidate_id,
        "cache_target_root": config.cache_target_root,
        "benchmark_matrix": str(config.benchmark_matrix or ""),
        "now": config.generated_at or DEFAULT_NOW,
    }


def map_child_exit(step: StepSpec, returncode: int) -> str:
    mapped = step.exit_map.get(str(returncode))
    if mapped:
        return normalize_status(mapped)
    if returncode == 0:
        return "PASS"
    return "FAILURE"


def run_step(config: RunConfig, step: StepSpec) -> StepResult:
    timeout = config.timeout_override if config.timeout_override is not None else step.timeout_s
    available, detail = probe_step(step, repo_root=config.repo_root, python=config.python)
    if not available:
        return StepResult(
            spec=step,
            status="NOT_AVAILABLE",
            exit_code=None,
            reason="command_not_available",
            probe_detail=detail,
            note="Missing commands are NOT_AVAILABLE; they are never treated as PASS.",
        )
    if step.network:
        return StepResult(
            spec=step,
            status="BLOCKED",
            exit_code=None,
            reason="network_step_blocked",
            probe_detail=detail,
        )
    if step.solver and not config.allow_solver:
        return StepResult(
            spec=step,
            status="BLOCKED",
            exit_code=None,
            reason="solver_requires_allow_solver",
            probe_detail=detail,
        )
    if step.kind == "builtin":
        return _run_builtin(config, step, timeout=timeout, probe_detail=detail)

    argv = resolve_argv(step.argv_template, mapping_for(config, step))
    try:
        assert_allowed_command(
            argv,
            allow_solver=config.allow_solver,
            repo_root=config.repo_root,
            output_dir=config.output_dir,
            declared_repo_paths_ok=step.declared_repo_paths_ok,
        )
    except SafetyError as exc:
        return StepResult(
            spec=step,
            status="BLOCKED",
            exit_code=None,
            argv=argv,
            reason=str(exc),
            probe_detail=detail,
        )
    return _run_subprocess(config, step, argv, timeout=timeout, probe_detail=detail)


def _run_subprocess(
    config: RunConfig,
    step: StepSpec,
    argv: list[str],
    *,
    timeout: int,
    probe_detail: str,
) -> StepResult:
    step_dir = config.output_dir / "steps" / step.id
    step_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = assert_write_path(step_dir / "stdout.txt", config.output_dir)
    stderr_path = assert_write_path(step_dir / "stderr.txt", config.output_dir)
    env = sanitize_env()
    env["PYTHONPATH"] = (
        str(config.repo_root)
        + (os_pathsep() + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    )
    started = time.monotonic()
    try:
        completed = subprocess.run(
            argv,
            cwd=str(config.repo_root),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_path.write_text((exc.stderr or "") + "\ntimeout\n", encoding="utf-8")
        return StepResult(
            spec=step,
            status="FAILURE",
            exit_code=None,
            argv=argv,
            reason=f"timeout_after_{timeout}s",
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            duration_s=round(time.monotonic() - started, 4),
            probe_detail=probe_detail,
        )
    except OSError as exc:
        return StepResult(
            spec=step,
            status="NOT_AVAILABLE",
            exit_code=None,
            argv=argv,
            reason=f"os_error:{exc}",
            probe_detail=probe_detail,
        )
    stdout_path.write_text(completed.stdout or "", encoding="utf-8")
    stderr_path.write_text(completed.stderr or "", encoding="utf-8")
    status = map_child_exit(step, int(completed.returncode))
    return StepResult(
        spec=step,
        status=status,
        exit_code=int(completed.returncode),
        argv=argv,
        reason=None if status == "PASS" else f"child_exit_{completed.returncode}",
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
        duration_s=round(time.monotonic() - started, 4),
        probe_detail=probe_detail,
    )


def os_pathsep() -> str:
    import os

    return os.pathsep


def _run_builtin(config: RunConfig, step: StepSpec, *, timeout: int, probe_detail: str) -> StepResult:
    name = step.builtin or step.id
    started = time.monotonic()
    try:
        if name == "repository_state":
            payload, status, reason = _builtin_repository_state(config, timeout=timeout)
        elif name == "finite_json_no_network":
            payload, status, reason = _builtin_finite_json(config)
        else:
            return StepResult(
                spec=step,
                status="NOT_AVAILABLE",
                exit_code=None,
                reason=f"unknown_builtin:{name}",
                probe_detail=probe_detail,
            )
    except SafetyError as exc:
        return StepResult(
            spec=step,
            status="BLOCKED",
            exit_code=None,
            reason=str(exc),
            probe_detail=probe_detail,
            duration_s=round(time.monotonic() - started, 4),
        )
    step_dir = config.output_dir / "steps" / step.id
    step_dir.mkdir(parents=True, exist_ok=True)
    out = assert_write_path(step_dir / "result.json", config.output_dir)
    out.write_text(dumps(payload) + "\n", encoding="utf-8")
    return StepResult(
        spec=step,
        status=status,
        exit_code=0 if status == "PASS" else None,
        argv=[f"builtin:{name}"],
        reason=reason,
        duration_s=round(time.monotonic() - started, 4),
        probe_detail=probe_detail,
        note=payload.get("note") if isinstance(payload, dict) else None,
    )


def _git(config: RunConfig, args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    argv = ["git", "-C", str(config.repo_root), *args]
    assert_allowed_command(
        argv,
        allow_solver=False,
        repo_root=config.repo_root,
        output_dir=config.output_dir,
    )
    return subprocess.run(
        argv,
        cwd=str(config.repo_root),
        env=sanitize_env(),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _builtin_repository_state(config: RunConfig, *, timeout: int) -> tuple[dict[str, Any], str, str | None]:
    head = _git(config, ["rev-parse", "HEAD"], timeout)
    branch = _git(config, ["rev-parse", "--abbrev-ref", "HEAD"], timeout)
    status = _git(config, ["status", "--porcelain"], timeout)
    if any(proc.returncode != 0 for proc in (head, branch, status)):
        payload = {
            "head": None,
            "branch": None,
            "dirty": None,
            "status_porcelain": None,
            "errors": [head.stderr, branch.stderr, status.stderr],
        }
        return payload, "FAILURE", "git_read_failed"
    porcelain = status.stdout
    payload = {
        "head": head.stdout.strip() or None,
        "branch": branch.stdout.strip() or None,
        "dirty": bool(porcelain.strip()),
        "status_porcelain": porcelain,
        "read_only": True,
        "mutated_git": False,
        "note": "Read-only git inspection. No merge, reset, push, or branch rewrite.",
    }
    return payload, "PASS", None


def _builtin_finite_json(config: RunConfig) -> tuple[dict[str, Any], str, str | None]:
    env = sanitize_env()
    network_env_present = [key for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY") if env.get(key)]
    scanned: list[dict[str, Any]] = []
    bad: list[str] = []
    for path in sorted(config.output_dir.rglob("*.json")):
        if path.name.startswith("."):
            continue
        rel = str(path.relative_to(config.output_dir))
        text = path.read_text(encoding="utf-8")
        record: dict[str, Any] = {"path": rel, "finite": True, "error": None}
        if text_has_nonfinite_tokens(text):
            record["finite"] = False
            record["error"] = "nonfinite_token"
            bad.append(rel)
        else:
            try:
                load_finite_json(text)
            except ValueError as exc:
                record["finite"] = False
                record["error"] = str(exc)
                bad.append(rel)
        scanned.append(record)
    helper_ok = shared_json_helper_available()
    payload = {
        "shared_json_helper_available": helper_ok,
        "shared_json_helper": "tools.streaming.memory_telemetry.json_safe",
        "network_env_cleared": network_env_present == [],
        "network_env_present": network_env_present,
        "files_scanned": scanned,
        "nonfinite_files": bad,
        "note": "Finite JSON check is infrastructure-only. It is not a scientific PASS.",
    }
    if not helper_ok:
        return payload, "NOT_AVAILABLE", "shared_json_helper_missing"
    if network_env_present:
        return payload, "BLOCKED", "network_env_present"
    if bad:
        return payload, "FAILURE", "nonfinite_json"
    return payload, "PASS", None


def run_audit(config: RunConfig) -> tuple[dict[str, Any], int]:
    config = apply_fixture_defaults(config)
    results = [run_step(config, step) for step in selected_steps(config)]
    git_state = _load_step_json(config.output_dir / "steps" / "repository_state" / "result.json")
    overall = aggregate_statuses(item.status for item in results)
    report = build_report(
        repo_root=config.repo_root,
        output_dir=config.output_dir,
        generated_at=config.generated_at,
        git_state=git_state,
        steps=[item.to_dict() for item in results],
        overall_status=overall,
        allow_solver=config.allow_solver,
        catalog_path=str(config.catalog.path),
        shell_family=config.shell_family,
    )
    paths = write_report_files(report, config.output_dir)
    report["report_paths"] = paths
    if config.emit_surfaces_enabled:
        report["surfaces"] = emit_surfaces(report, config.output_dir)
        # Rewrite report so surfaces are included in the finite JSON.
        write_report_files(report, config.output_dir)
    return report, status_to_exit(overall)


def _load_step_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = load_finite_json(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def config_from_namespace(ns: Any, *, repo_root: Path, output_dir: Path, catalog: Catalog) -> RunConfig:
    step_ids = None
    if getattr(ns, "steps", None):
        step_ids = tuple(part.strip() for part in str(ns.steps).split(",") if part.strip())
    return RunConfig(
        repo_root=repo_root,
        output_dir=output_dir,
        catalog=catalog,
        python=str(getattr(ns, "python", None) or sys.executable),
        allow_solver=bool(getattr(ns, "allow_solver", False)),
        include_optional=bool(getattr(ns, "include_optional", False)),
        step_ids=step_ids,
        generated_at=getattr(ns, "now", None) or DEFAULT_NOW,
        shell_family=str(getattr(ns, "shell_family", "posix")),
        registry=_opt_path(getattr(ns, "registry", None)),
        claims=_opt_path(getattr(ns, "claims", None)),
        empirical_manifest=_opt_path(getattr(ns, "empirical_manifest", None)),
        provenance=_opt_path(getattr(ns, "provenance", None)),
        research_state_manifest=_opt_path(getattr(ns, "research_state_manifest", None)),
        performance_pair=_opt_path(getattr(ns, "performance_pair", None)),
        candidates=_opt_path(getattr(ns, "candidates", None)),
        candidate_id=str(getattr(ns, "candidate_id", None) or "2363a3d50984c392"),
        cache_target_root=str(getattr(ns, "cache_target_root", None) or DEFAULT_CACHE_TARGET),
        benchmark_matrix=_opt_path(getattr(ns, "benchmark_matrix", None)),
        timeout_override=getattr(ns, "timeout_s", None),
        emit_surfaces_enabled=not bool(getattr(ns, "no_surfaces", False)),
    )


def _opt_path(value: Any) -> Path | None:
    if value in (None, ""):
        return None
    return Path(value)
