"""Explicit request/result contracts for local solver adapters."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence


class AdapterState(str, Enum):
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    BLOCKED = "BLOCKED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


@dataclass(frozen=True)
class ResourceBudget:
    timeout_s: float = 30.0
    max_stdout_bytes: int = 16_384
    max_stderr_bytes: int = 16_384
    max_output_bytes: int | None = None
    max_memory_bytes: int | None = None


@dataclass(frozen=True)
class AdapterRequest:
    """A complete declaration; no field is inferred from a workload directory."""

    workload_id: str
    command: tuple[str, ...]
    allowed_commands: Mapping[str, tuple[str, ...]]
    code_commit: str
    configuration: Mapping[str, Any]
    seed: int
    input_identity: str
    provenance: Mapping[str, Any]
    output_root: Path
    evidence_class: str
    expected_outputs: tuple[str, ...] = ("result.json",)
    completion_manifest: str = "completion_manifest.json"
    resource_budget: ResourceBudget = field(default_factory=ResourceBudget)
    network_disabled: bool = True
    run_id: str | None = None
    resume: bool = True

    @classmethod
    def make(
        cls,
        *,
        workload_id: str,
        command: Sequence[str],
        allowed_commands: Mapping[str, Sequence[str]],
        code_commit: str,
        configuration: Mapping[str, Any],
        seed: int,
        input_identity: str,
        provenance: Mapping[str, Any],
        output_root: str | Path,
        evidence_class: str,
        expected_outputs: Sequence[str] = ("result.json",),
        completion_manifest: str = "completion_manifest.json",
        resource_budget: ResourceBudget | None = None,
        network_disabled: bool = True,
        run_id: str | None = None,
        resume: bool = True,
    ) -> "AdapterRequest":
        return cls(
            workload_id=str(workload_id),
            command=tuple(str(item) for item in command),
            allowed_commands={str(key): tuple(str(item) for item in value) for key, value in allowed_commands.items()},
            code_commit=str(code_commit),
            configuration=dict(configuration),
            seed=int(seed),
            input_identity=str(input_identity),
            provenance=dict(provenance),
            output_root=Path(output_root),
            evidence_class=str(evidence_class),
            expected_outputs=tuple(str(item) for item in expected_outputs),
            completion_manifest=str(completion_manifest),
            resource_budget=resource_budget or ResourceBudget(),
            network_disabled=bool(network_disabled),
            run_id=run_id,
            resume=bool(resume),
        )

@dataclass(frozen=True)
class AdapterResult:
    state: AdapterState
    report: dict[str, Any]
