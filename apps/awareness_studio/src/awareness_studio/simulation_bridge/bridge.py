"""Fail-closed Awareness Studio integration for local simulation execution.

The bridge is an adapter, not an executor.  It accepts only an exact argv
already registered by the caller and delegates execution to the canonical
bounded runner.  Artifacts are imported only after checksum, finite-JSON,
provenance, configuration, and read-only lineage checks succeed.

All returned states are engineering workflow states.  This module never
creates scientific PASS, a Bayes factor, empirical evidence, or a causal claim.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

_PLACEHOLDERS = {"", "unknown", "null", "none", "n/a", "na", "placeholder"}
_REQUIRED_PROVENANCE = ("dataset_id", "source", "data_mode")
_SYNTHETIC_MODES = {"synthetic", "synthetic_demo", "synthetic_demo_only"}


class BridgeState(str, Enum):
    PLANNING = "PLANNING"
    EXECUTION_NOT_AVAILABLE = "EXECUTION_NOT_AVAILABLE"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    ENGINEERING_EXECUTION_COMPLETE = "ENGINEERING_EXECUTION_COMPLETE"
    EVIDENCE_READY_FOR_REVIEW = "EVIDENCE_READY_FOR_REVIEW"


@dataclass(frozen=True)
class ResourceBudget:
    timeout_s: float
    memory_budget_bytes: int | None
    disk_budget_bytes: int | None
    stdout_limit: int = 16_384
    stderr_limit: int = 16_384

    def validate(self) -> list[str]:
        errors: list[str] = []
        if (
            isinstance(self.timeout_s, bool)
            or not isinstance(self.timeout_s, (int, float))
            or not math.isfinite(float(self.timeout_s))
            or self.timeout_s <= 0
        ):
            errors.append("resource timeout_s must be finite and positive")
        for name, value in (
            ("memory_budget_bytes", self.memory_budget_bytes),
            ("disk_budget_bytes", self.disk_budget_bytes),
        ):
            if value is None:
                errors.append(f"resource {name} must be explicit for registered execution")
            elif isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                errors.append(f"resource {name} must be a positive integer")
        for name, value in (("stdout_limit", self.stdout_limit), ("stderr_limit", self.stderr_limit)):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                errors.append(f"resource {name} must be a positive integer")
        return errors


@dataclass(frozen=True)
class RegisteredWorkload:
    workload_id: str
    argv: tuple[str, ...]
    expected_outputs: tuple[str, ...] = ("unit_manifest.json", "RunRecord.json", "summary.json")

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.workload_id.strip():
            errors.append("workload_id is required")
        if not self.argv or any(not str(item).strip() for item in self.argv):
            errors.append("workload argv must be non-empty")
        if len(set(self.expected_outputs)) != len(self.expected_outputs):
            errors.append("expected_outputs must be unique")
        required = {"unit_manifest.json", "RunRecord.json"}
        if not required.issubset(self.expected_outputs):
            errors.append("unit_manifest.json and RunRecord.json are required")
        if not ({"summary.json", "metrics.json", "metrics.csv"} & set(self.expected_outputs)):
            errors.append("summary.json, metrics.json, or metrics.csv is required")
        for relative in self.expected_outputs:
            path = Path(relative)
            if not relative or path.is_absolute() or ".." in path.parts:
                errors.append(f"expected output escapes output root: {relative!r}")
        return errors


class WorkloadRegistry:
    """In-memory allowlist; arbitrary argv is never accepted at run time."""

    def __init__(self, workloads: Sequence[RegisteredWorkload] = ()):
        self._workloads: dict[str, RegisteredWorkload] = {}
        for workload in workloads:
            self.register(workload)

    def register(self, workload: RegisteredWorkload) -> None:
        errors = workload.validate()
        if errors:
            raise ValueError("invalid registered workload: " + "; ".join(errors))
        if workload.workload_id in self._workloads:
            raise ValueError(f"workload already registered: {workload.workload_id}")
        self._workloads[workload.workload_id] = workload

    def get(self, workload_id: str) -> RegisteredWorkload | None:
        return self._workloads.get(workload_id)


@dataclass(frozen=True)
class BridgeRequest:
    workload_id: str
    run_id: str
    code_commit: str
    configuration: Mapping[str, Any]
    seed: int
    input_identity: str
    provenance: Mapping[str, Any]
    output_root: Path
    resource_budget: ResourceBudget
    authorize_execution: bool = False
    network_enabled: bool = False
    resume: bool = True

    def validate(self, workload: RegisteredWorkload | None) -> list[str]:
        errors: list[str] = []
        if workload is None:
            errors.append(f"workload is not registered: {self.workload_id}")
        if not isinstance(self.run_id, str) or not self.run_id.strip() or self.run_id.lower() in _PLACEHOLDERS or Path(self.run_id).name != self.run_id:
            errors.append("run_id must be a non-placeholder path-safe identity")
        if not isinstance(self.code_commit, str) or not self.code_commit.strip() or self.code_commit.lower() in _PLACEHOLDERS:
            errors.append("code_commit must be explicit and non-placeholder")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            errors.append("seed must be an integer")
        if not isinstance(self.input_identity, str) or not self.input_identity.strip() or self.input_identity.lower() in _PLACEHOLDERS:
            errors.append("input_identity must be explicit and non-placeholder")
        if not isinstance(self.provenance, Mapping):
            errors.append("provenance must be a mapping")
        else:
            for key in _REQUIRED_PROVENANCE:
                value = str(self.provenance.get(key, "")).strip()
                if not value or value.lower() in _PLACEHOLDERS:
                    errors.append(f"provenance.{key} is required and cannot be a placeholder")
        if not isinstance(self.configuration, Mapping):
            errors.append("configuration must be a mapping")
        else:
            try:
                json.dumps(self.configuration, sort_keys=True, allow_nan=False)
            except (TypeError, ValueError) as exc:
                errors.append(f"configuration is not finite JSON: {exc}")
        errors.extend(self.resource_budget.validate())
        if self.network_enabled:
            errors.append("Awareness Studio bridge denies network-enabled execution")
        try:
            root = self.output_root.resolve()
            if not str(self.output_root).strip() or root == Path(self.output_root.anchor):
                errors.append("output_root must be an explicit non-root path")
            if "://" in str(self.output_root):
                errors.append("output_root must be a local path")
        except (OSError, RuntimeError, ValueError) as exc:
            errors.append(f"output_root is invalid: {exc}")
        return errors


@dataclass
class BridgeResult:
    state: BridgeState
    request: BridgeRequest
    execution_state: str | None = None
    accepted_artifacts: list[dict[str, Any]] = field(default_factory=list)
    rejected_artifacts: list[dict[str, Any]] = field(default_factory=list)
    runner_manifest: Mapping[str, Any] | None = None
    lineage_report: Mapping[str, Any] | None = None
    diagnostics: list[str] = field(default_factory=list)
    evidence_class: str = "engineering_execution"

    @property
    def scientific_pass(self) -> bool:
        return False

    @property
    def formal_bayes_factor(self) -> None:
        return None

    def to_release_bundle(self) -> dict[str, Any]:
        """Project verified runtime facts into the existing release contract."""
        manifest = self.runner_manifest or {}
        unit = SimulationBridge._unit_record(manifest) or {}
        state = str(unit.get("state") or self.execution_state or "NOT_RUN")
        passed = self.state in {
            BridgeState.ENGINEERING_EXECUTION_COMPLETE,
            BridgeState.EVIDENCE_READY_FOR_REVIEW,
        }
        lineage = self.lineage_report or {}
        accepted = list(self.accepted_artifacts)
        synthetic = self.evidence_class == "synthetic_demo_only"
        return {
            "bundle_schema": "research_cycle_release_bundle.v1",
            "cycle_id": f"simulation:{self.request.run_id}",
            "source_manifest_present": bool(self.request.input_identity),
            "source_manifest_path": f"registered-workload:{self.request.workload_id}",
            "checksums_present": bool(accepted) and passed,
            "checksum_entries": accepted,
            "configuration_locked": True,
            "code_commit": self.request.code_commit,
            "seed": self.request.seed,
            "input_provenance_complete": passed,
            "input_provenance_missing": [] if passed else ["verified_execution_output"],
            "outputs_finite": True if passed else None,
            "non_finite_metric_paths": [],
            "metrics": {},
            "work_units": [
                {
                    "id": unit.get("unit_id", self.request.run_id),
                    "status": state.lower(),
                    "partial": state == "PARTIAL",
                    "output_checksums": [item["sha256"] for item in accepted if item.get("sha256")],
                    "input_checksums": [self.request.input_identity],
                }
            ] if unit else [],
            "all_work_units_terminal": bool(unit) and state in {"PASS", "FAILED", "TIMEOUT", "BLOCKED", "PARTIAL", "INFRASTRUCTURE_FAILURE"},
            "partial_runs_explicitly_marked": state != "PARTIAL" or bool(unit),
            "artifact_lineage_complete": lineage.get("status") == "COMPLETE" if lineage else None,
            "artifact_lineage_missing": [] if lineage.get("status") == "COMPLETE" else ["lineage_report"],
            "validation_report_present": bool(lineage),
            "validation_status": "ok" if passed and lineage.get("status") == "COMPLETE" else "failed",
            "null_metadata_applicable": False,
            "null_metadata_present": False,
            "multiplicity_metadata_applicable": False,
            "multiplicity_metadata_present": False,
            "forecasting_applicable": False,
            "resource_budgets_respected": passed,
            "resource_budget_details": {
                "timeout_s": self.request.resource_budget.timeout_s,
                "memory_budget_bytes": self.request.resource_budget.memory_budget_bytes,
                "disk_budget_bytes": self.request.resource_budget.disk_budget_bytes,
                "executor_state": state,
                "budget_exceeded": not passed,
            },
            "full_dataset_download": False,
            "network_policy_recorded": manifest.get("runner", {}).get("network_disabled") is True if isinstance(manifest.get("runner"), Mapping) else None,
            "network_policy_violated": False,
            "evidence_classes": [self.evidence_class] if passed else [],
            "evidence_classes_consistent": True if passed else None,
            "synthetic_only": synthetic if passed else None,
            "proxy_only": False if passed else None,
            "empirical_present": False if passed else None,
            "report_metadata_text": "Bounded local solver execution artifact only; no empirical interpretation.",
            "infrastructure_blocked": False if passed else None,
            "comparable": True if passed else None,
            "comparability_notes": ["Single deterministic engineering smoke run; no scientific comparison claimed."],
        }

    def release_review(self) -> dict[str, Any]:
        """Run the repository release evaluator over this verified result."""
        from tools.research_cycle_release.evaluator import evaluate_research_cycle_release

        return evaluate_research_cycle_release(self.to_release_bundle(), adapter_hint="generic").to_dict()

    def to_dict(self) -> dict[str, Any]:
        return _finite(
            {
                "schema_version": "AwarenessStudio.SimulationBridge.v1",
                "state": self.state.value,
                "workload_id": self.request.workload_id,
                "run_id": self.request.run_id,
                "authorize_execution": self.request.authorize_execution,
                "network_enabled": self.request.network_enabled,
                "execution_state": self.execution_state,
                "accepted_artifacts": self.accepted_artifacts,
                "rejected_artifacts": self.rejected_artifacts,
                "runner_manifest": self.runner_manifest,
                "lineage_report": self.lineage_report,
                "diagnostics": self.diagnostics,
                "metrics": None,
                "scientific_pass": False,
                "formal_bayes_factor": None,
                "evidence_class": self.evidence_class,
                "claim_scope": "Engineering execution and artifact review only; not scientific evidence or causal validation.",
            }
        )


def _finite(value: Any, path: str = "$") -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} contains non-finite value")
        return value
    if isinstance(value, Mapping):
        return {str(key): _finite(item, f"{path}.{key}") for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite(item, f"{path}[{index}]") for index, item in enumerate(value)]
    return str(value)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_finite_json(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
        return json.loads(text, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(f"non-finite token {token}")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"invalid finite JSON in {path.name}: {exc}") from exc


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class SimulationBridge:
    """Awareness Studio adapter over the canonical bounded local executor."""

    def __init__(self, registry: WorkloadRegistry):
        self.registry = registry

    def plan(self, request: BridgeRequest) -> BridgeResult:
        workload = self.registry.get(request.workload_id)
        errors = request.validate(workload)
        if errors:
            return BridgeResult(BridgeState.EXECUTION_NOT_AVAILABLE, request, diagnostics=errors)
        return BridgeResult(
            BridgeState.PLANNING,
            request,
            diagnostics=["dry-run planning only; canonical executor was not invoked"],
        )

    def run(self, request: BridgeRequest) -> BridgeResult:
        planned = self.plan(request)
        if planned.state is not BridgeState.PLANNING or not request.authorize_execution:
            return planned

        repo_root = Path(__file__).resolve().parents[5]
        if (repo_root / "tools" / "simulation_execution").is_dir():
            if str(repo_root) in sys.path:
                sys.path.remove(str(repo_root))
            sys.path.insert(0, str(repo_root))
        try:
            from tools.simulation_execution.models import RunnerConfig, WorkUnit
            from tools.simulation_execution.runner import run_plan
        except (ImportError, ModuleNotFoundError, AttributeError) as exc:
            return BridgeResult(
                BridgeState.EXECUTION_NOT_AVAILABLE,
                request,
                diagnostics=[f"canonical bounded executor unavailable: {type(exc).__name__}: {exc}"],
            )

        root = request.output_root.resolve()
        output_dir = (root / request.run_id).resolve()
        try:
            output_dir.relative_to(root)
        except ValueError:
            return BridgeResult(BridgeState.EXECUTION_FAILED, request, diagnostics=["output directory escapes explicit output root"])

        workload = self.registry.get(request.workload_id)
        assert workload is not None  # plan() validated registration
        unit = WorkUnit.make(
            request.run_id,
            workload.workload_id,
            workload.argv,
            output_dir,
            expected_outputs=workload.expected_outputs,
            input_references=(request.input_identity,),
            seed=request.seed,
            config=dict(request.configuration),
            timeout_s=request.resource_budget.timeout_s,
        )
        config = RunnerConfig(
            output_root=root,
            allowed_commands={workload.workload_id: workload.argv},
            default_timeout_s=request.resource_budget.timeout_s,
            stdout_limit=request.resource_budget.stdout_limit,
            stderr_limit=request.resource_budget.stderr_limit,
            runtime_budget_s=request.resource_budget.timeout_s,
            memory_budget_bytes=request.resource_budget.memory_budget_bytes,
            disk_budget_bytes=request.resource_budget.disk_budget_bytes,
            network_disabled=True,
            code_revision=request.code_commit,
            deterministic_seed=request.seed,
        )
        try:
            manifest = run_plan([unit], config, resume=request.resume)
        except Exception as exc:
            return BridgeResult(
                BridgeState.EXECUTION_FAILED,
                request,
                diagnostics=[f"canonical executor failed before producing a manifest: {exc}"],
            )
        unit_record = self._unit_record(manifest)
        execution_state = str(unit_record.get("state")) if unit_record else None
        if execution_state != "PASS":
            return BridgeResult(
                BridgeState.EXECUTION_FAILED,
                request,
                execution_state=execution_state,
                runner_manifest=manifest,
                diagnostics=["canonical execution did not produce a PASS unit; no artifacts imported"],
            )
        return self._verify_pass(request, workload, output_dir, manifest, unit_record)

    @staticmethod
    def _unit_record(manifest: Mapping[str, Any]) -> Mapping[str, Any] | None:
        units = manifest.get("units")
        if not isinstance(units, Sequence) or isinstance(units, (str, bytes)) or len(units) != 1 or not isinstance(units[0], Mapping):
            return None
        return units[0]

    def _verify_pass(
        self,
        request: BridgeRequest,
        workload: RegisteredWorkload,
        output_dir: Path,
        manifest: Mapping[str, Any],
        unit: Mapping[str, Any],
    ) -> BridgeResult:
        diagnostics: list[str] = []
        rejected: list[dict[str, Any]] = []
        accepted: list[dict[str, Any]] = []
        checksums = unit.get("checksums") if isinstance(unit.get("checksums"), Mapping) else {}
        root = request.output_root.resolve()
        loaded: dict[str, Any] = {}

        for relative in workload.expected_outputs:
            candidate = (output_dir / relative).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                rejected.append({"relative_path": relative, "reason": "output escapes output root"})
                continue
            expected = checksums.get(relative)
            if not isinstance(expected, str) or not expected:
                rejected.append({"relative_path": relative, "reason": "canonical checksum is missing"})
                continue
            if not candidate.is_file():
                rejected.append({"relative_path": relative, "reason": "expected artifact is missing"})
                continue
            actual = _sha256(candidate)
            if actual != expected:
                rejected.append({"relative_path": relative, "reason": "canonical checksum mismatch"})
                continue
            if candidate.suffix.lower() == ".json":
                try:
                    loaded[relative] = _load_finite_json(candidate)
                except ValueError as exc:
                    rejected.append({"relative_path": relative, "reason": str(exc)})
                    continue
            accepted.append({"relative_path": relative, "sha256": actual, "size_bytes": candidate.stat().st_size})

        record = loaded.get("RunRecord.json")
        diagnostics.extend(self._validate_record(request, workload, record))
        unit_manifest = loaded.get("unit_manifest.json")
        if not isinstance(unit_manifest, Mapping) or unit_manifest.get("work_unit_id") != request.run_id or unit_manifest.get("complete") is not True:
            diagnostics.append("unit_manifest.json does not bind a complete requested work unit")
        summary = loaded.get("summary.json")
        if isinstance(summary, Mapping):
            if summary.get("evidence_class") != (record or {}).get("evidence_class"):
                diagnostics.append("summary evidence class is inconsistent with RunRecord")
            if summary.get("scientific_pass") is True or summary.get("formal_bayes_factor") is not None:
                diagnostics.append("summary contains forbidden scientific result fields")

        lineage: Mapping[str, Any] | None = None
        if not diagnostics and not rejected:
            try:
                from tools.simulation_artifacts.extractor import extract_run

                lineage = extract_run(output_dir)
            except Exception as exc:
                diagnostics.append(f"artifact lineage verification unavailable: {exc}")
            if lineage is not None and lineage.get("status") != "COMPLETE":
                diagnostics.append(f"artifact lineage is not complete: {lineage.get('status')}")
            if lineage is not None:
                by_path = {
                    str(item.get("relative_path")): item
                    for item in lineage.get("artifact_manifest", {}).get("artifacts", [])
                    if isinstance(item, Mapping)
                }
                for relative in by_path:
                    try:
                        (output_dir / relative).resolve().relative_to(output_dir.resolve())
                    except ValueError:
                        diagnostics.append(f"artifact lineage path escapes output directory: {relative}")
                for item in accepted:
                    if by_path.get(item["relative_path"], {}).get("sha256") != item["sha256"]:
                        diagnostics.append(f"artifact lineage checksum mismatch: {item['relative_path']}")
                provenance = lineage.get("provenance") if isinstance(lineage.get("provenance"), Mapping) else {}
                for key in ("run_id", "dataset_id", "source", "data_mode", "git_commit"):
                    expected = request.run_id if key == "run_id" else request.code_commit if key == "git_commit" else request.provenance.get(key)
                    if str(provenance.get(key, "")) != str(expected):
                        diagnostics.append(f"artifact lineage {key} is inconsistent with request")
                if provenance.get("evidence_class") != (record or {}).get("evidence_class"):
                    diagnostics.append("artifact lineage evidence class is inconsistent with RunRecord")

        if diagnostics or rejected:
            return BridgeResult(
                BridgeState.EXECUTION_FAILED,
                request,
                execution_state="PASS",
                accepted_artifacts=[],
                rejected_artifacts=rejected,
                runner_manifest=manifest,
                lineage_report=lineage,
                diagnostics=diagnostics or ["artifact verification rejected output"],
                evidence_class="engineering_execution",
            )

        synthetic = bool(record.get("synthetic")) or str(record.get("data_mode", "")).lower() in _SYNTHETIC_MODES if record else False
        evidence_class = "synthetic_demo_only" if synthetic else "engineering_simulation_artifact"
        state = BridgeState.ENGINEERING_EXECUTION_COMPLETE if synthetic else BridgeState.EVIDENCE_READY_FOR_REVIEW
        return BridgeResult(
            state,
            request,
            execution_state="PASS",
            accepted_artifacts=accepted,
            runner_manifest=manifest,
            lineage_report=lineage,
            diagnostics=["checksums, finite JSON, provenance, configuration, and artifact lineage verified"],
            evidence_class=evidence_class,
        )

    @staticmethod
    def _validate_record(request: BridgeRequest, workload: RegisteredWorkload, record: Any) -> list[str]:
        if not isinstance(record, Mapping):
            return ["RunRecord.json must contain a JSON object"]
        errors: list[str] = []
        for key in ("run_id", "created_at", "source", "dataset_id", "data_mode", "git_commit", "evidence_class"):
            value = str(record.get(key, "")).strip()
            if not value or value.lower() in _PLACEHOLDERS:
                errors.append(f"RunRecord provenance missing or placeholder: {key}")
        if record.get("run_id") != request.run_id:
            errors.append("RunRecord run_id does not match request")
        for key in _REQUIRED_PROVENANCE:
            actual = str(record.get(key, ""))
            expected = str(request.provenance.get(key, ""))
            matches = actual.lower() == expected.lower() if key == "data_mode" else actual == expected
            if not matches:
                errors.append(f"RunRecord {key} does not match request provenance")
        if record.get("git_commit") != request.code_commit:
            errors.append("RunRecord git_commit does not match requested code_commit")
        raw_seed = record.get("seed")
        if isinstance(raw_seed, bool) or not isinstance(raw_seed, int) or raw_seed != request.seed:
            errors.append("RunRecord seed does not match requested seed")
        input_identity = record.get("input_identity")
        if input_identity is None and isinstance(record.get("input"), Mapping):
            input_identity = record["input"].get("identity") or record["input"].get("input_identity")
        if input_identity != request.input_identity:
            errors.append("RunRecord input identity does not match request")
        if not isinstance(record.get("metrics"), Mapping):
            errors.append("RunRecord metrics must be an object")
        if not isinstance(record.get("artifacts"), Mapping):
            errors.append("RunRecord artifacts must be an object")
        else:
            for name, value in record["artifacts"].items():
                path = Path(str(value))
                if path.is_absolute() or ".." in path.parts or path.name not in workload.expected_outputs:
                    errors.append(f"RunRecord artifact reference is not a declared output: {name}={value!r}")
        if record.get("configuration") is not None and _canonical(record.get("configuration")) != _canonical(dict(request.configuration)):
            errors.append("RunRecord configuration does not match request")
        if record.get("scientific_pass") is True:
            errors.append("RunRecord scientific_pass must remain false")
        if record.get("formal_bayes_factor") is not None:
            errors.append("RunRecord formal_bayes_factor must remain null")
        expected_synthetic = str(request.provenance.get("data_mode", "")).lower() in _SYNTHETIC_MODES
        if expected_synthetic:
            if record.get("synthetic") is not True or record.get("evidence_class") != "synthetic_demo_only":
                errors.append("synthetic execution must retain synthetic_demo_only classification")
        elif record.get("synthetic") is True or record.get("evidence_class") == "synthetic_demo_only":
            errors.append("non-synthetic execution cannot be classified synthetic_demo_only")
        return errors


__all__ = [
    "BridgeRequest",
    "BridgeResult",
    "BridgeState",
    "RegisteredWorkload",
    "ResourceBudget",
    "SimulationBridge",
    "WorkloadRegistry",
]
