"""BenchmarkPackV1 -- the outcome of building a `BenchmarkPackSpecV1`:
a curated, deterministic index over the `ReportPackV1`/`HtmlReportPackV1`
artifacts a `job_runner.batch` run produced. `BenchmarkPackIndexV1` is
the record of rendering that pack's static HTML index (see
`benchmark_packs.renderer`).

`benchmark_pack_id` is content-addressed over `source_spec_id`/`batch_id`/
sorted `report_pack_ids`/sorted `html_pack_ids`, without its own separate
`created_at` -- `batch_id` (from `job_runner.batch_manifest`) already
anchors this pack to a specific execution event, the same "result_id
doesn't need its own created_at" reasoning `job_runner.result` already
established for `PipelineJobResultV1`. `index_id` follows the same
pattern, anchored by `benchmark_pack_id` instead.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from benchmark_packs.validation import validate_benchmark_pack, validate_benchmark_pack_index

_SCHEMA_VERSION = "1"
_REPO_ROOT = Path(__file__).resolve().parents[1]

TEMPLATE_VERSION = "benchmark_packs.renderer v1"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _repo_commit() -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(_REPO_ROOT), capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception:
        pass
    return None


def compute_benchmark_pack_id(
    *, source_spec_id: str, batch_id: str, report_pack_ids: list[str], html_pack_ids: list[str],
) -> str:
    basis = {
        "source_spec_id": source_spec_id, "batch_id": batch_id,
        "report_pack_ids": sorted(report_pack_ids or []), "html_pack_ids": sorted(html_pack_ids or []),
    }
    return hashlib.sha256(_canonical_json(basis).encode("utf-8")).hexdigest()[:16]


def compute_index_id(*, benchmark_pack_id: str, linked_html_packs: list[str], template_version: str = TEMPLATE_VERSION) -> str:
    basis = {
        "benchmark_pack_id": benchmark_pack_id, "linked_html_packs": sorted(linked_html_packs or []),
        "template_version": template_version,
    }
    return hashlib.sha256(_canonical_json(basis).encode("utf-8")).hexdigest()[:16]


def benchmark_pack_blocked_interpretations_template() -> list[str]:
    """A fixed, deterministic list of prohibited interpretations for a
    benchmark pack -- not derived from pack content, mirroring
    `workflows.report_pack.blocked_interpretations_template`'s
    fixed-template convention, extended with pack-level items (a pack
    aggregates report packs, it does not add new evidentiary weight)."""
    return [
        "This benchmark pack does not support a clinical claim.",
        "This benchmark pack does not support a diagnostic claim.",
        "This benchmark pack does not support a treatment claim.",
        "This benchmark pack does not support a claim that any referenced artifact is a validated consciousness biomarker.",
        "This benchmark pack does not support a claim of spiritual/meditative attainment.",
        "This benchmark pack does not support a mechanistic-causal claim.",
        "This benchmark pack is not itself clinical evidence -- it is a curated collection of already-governed report packs.",
        "This benchmark pack does not promote the claim_scope_ceiling or evidence_level_ceiling of any referenced report pack.",
        "This benchmark pack does not mark any demo/synthetic output as validation-ready.",
        "Including a report pack in this benchmark pack does not itself constitute additional evidence beyond what that report pack already carries.",
    ]


class BenchmarkPackValidationError(ValueError):
    """Raised when a `BenchmarkPackV1` fails structural validation."""


class BenchmarkPackIndexValidationError(ValueError):
    """Raised when a `BenchmarkPackIndexV1` fails structural validation."""


@dataclass
class BenchmarkPackV1:
    schema_version: str = _SCHEMA_VERSION
    benchmark_pack_id: str = ""
    pack_name: str = ""
    pack_kind: str = "demo_pack"
    pack_purpose: str = ""
    source_spec_id: str = ""
    batch_id: str = ""
    job_ids: list[str] = field(default_factory=list)
    pipeline_ids: list[str] = field(default_factory=list)
    report_pack_ids: list[str] = field(default_factory=list)
    html_pack_ids: list[str] = field(default_factory=list)
    dataset_ids: list[str] = field(default_factory=list)
    modalities: list[str] = field(default_factory=list)
    input_modes: list[str] = field(default_factory=list)
    generated_report_pack_paths: list[str] = field(default_factory=list)
    generated_html_paths: list[str] = field(default_factory=list)
    generated_index_path: Optional[str] = None
    execution_summary: dict[str, Any] = field(default_factory=dict)
    coverage_summary: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    blocked_interpretations: list[str] = field(default_factory=benchmark_pack_blocked_interpretations_template)
    reproducibility_commands: list[str] = field(default_factory=list)
    created_at: str = ""
    repo_commit: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(
        cls, *, source_spec_id: str, batch_id: str, report_pack_ids: Optional[list[str]] = None,
        html_pack_ids: Optional[list[str]] = None, _now: Optional[datetime] = None, **kwargs: Any,
    ) -> "BenchmarkPackV1":
        kwargs["metadata"] = dict(kwargs.get("metadata") or {})
        report_pack_ids = list(report_pack_ids or [])
        html_pack_ids = list(html_pack_ids or [])
        benchmark_pack_id = compute_benchmark_pack_id(
            source_spec_id=source_spec_id, batch_id=batch_id,
            report_pack_ids=report_pack_ids, html_pack_ids=html_pack_ids,
        )
        ts = (_now or datetime.now(timezone.utc)).isoformat()
        return cls(
            benchmark_pack_id=benchmark_pack_id, source_spec_id=source_spec_id, batch_id=batch_id,
            report_pack_ids=report_pack_ids, html_pack_ids=html_pack_ids, created_at=ts,
            repo_commit=kwargs.pop("repo_commit", None) or _repo_commit(), **kwargs,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "benchmark_pack_id": self.benchmark_pack_id,
            "pack_name": self.pack_name,
            "pack_kind": self.pack_kind,
            "pack_purpose": self.pack_purpose,
            "source_spec_id": self.source_spec_id,
            "batch_id": self.batch_id,
            "job_ids": list(self.job_ids),
            "pipeline_ids": list(self.pipeline_ids),
            "report_pack_ids": list(self.report_pack_ids),
            "html_pack_ids": list(self.html_pack_ids),
            "dataset_ids": list(self.dataset_ids),
            "modalities": list(self.modalities),
            "input_modes": list(self.input_modes),
            "generated_report_pack_paths": list(self.generated_report_pack_paths),
            "generated_html_paths": list(self.generated_html_paths),
            "generated_index_path": self.generated_index_path,
            "execution_summary": dict(self.execution_summary or {}),
            "coverage_summary": dict(self.coverage_summary or {}),
            "limitations": list(self.limitations),
            "blocked_interpretations": list(self.blocked_interpretations),
            "reproducibility_commands": list(self.reproducibility_commands),
            "created_at": self.created_at,
            "repo_commit": self.repo_commit,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BenchmarkPackV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            benchmark_pack_id=d.get("benchmark_pack_id", ""),
            pack_name=d.get("pack_name", ""),
            pack_kind=d.get("pack_kind", "demo_pack"),
            pack_purpose=d.get("pack_purpose", ""),
            source_spec_id=d.get("source_spec_id", ""),
            batch_id=d.get("batch_id", ""),
            job_ids=list(d.get("job_ids") or []),
            pipeline_ids=list(d.get("pipeline_ids") or []),
            report_pack_ids=list(d.get("report_pack_ids") or []),
            html_pack_ids=list(d.get("html_pack_ids") or []),
            dataset_ids=list(d.get("dataset_ids") or []),
            modalities=list(d.get("modalities") or []),
            input_modes=list(d.get("input_modes") or []),
            generated_report_pack_paths=list(d.get("generated_report_pack_paths") or []),
            generated_html_paths=list(d.get("generated_html_paths") or []),
            generated_index_path=d.get("generated_index_path"),
            execution_summary=dict(d.get("execution_summary") or {}),
            coverage_summary=dict(d.get("coverage_summary") or {}),
            limitations=list(d.get("limitations") or []),
            blocked_interpretations=list(d.get("blocked_interpretations") or []),
            reproducibility_commands=list(d.get("reproducibility_commands") or []),
            created_at=d.get("created_at", ""),
            repo_commit=d.get("repo_commit"),
            metadata=dict(d.get("metadata") or {}),
        )

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_json(cls, text: str) -> "BenchmarkPackV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    def validate(self) -> list[str]:
        return validate_benchmark_pack(self)

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            raise BenchmarkPackValidationError("; ".join(errors))


@dataclass
class BenchmarkPackIndexV1:
    schema_version: str = _SCHEMA_VERSION
    index_id: str = ""
    benchmark_pack_id: str = ""
    title: str = ""
    output_root: str = ""
    index_html_path: Optional[str] = None
    linked_report_packs: list[str] = field(default_factory=list)
    linked_html_packs: list[str] = field(default_factory=list)
    sections_rendered: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    blocked_interpretations: list[str] = field(default_factory=benchmark_pack_blocked_interpretations_template)
    created_at: str = ""
    repo_commit: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(
        cls, *, benchmark_pack_id: str, linked_html_packs: Optional[list[str]] = None,
        _now: Optional[datetime] = None, **kwargs: Any,
    ) -> "BenchmarkPackIndexV1":
        kwargs["metadata"] = dict(kwargs.get("metadata") or {})
        linked_html_packs = list(linked_html_packs or [])
        index_id = compute_index_id(benchmark_pack_id=benchmark_pack_id, linked_html_packs=linked_html_packs)
        ts = (_now or datetime.now(timezone.utc)).isoformat()
        return cls(
            index_id=index_id, benchmark_pack_id=benchmark_pack_id, linked_html_packs=linked_html_packs,
            created_at=ts, repo_commit=kwargs.pop("repo_commit", None) or _repo_commit(), **kwargs,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "index_id": self.index_id,
            "benchmark_pack_id": self.benchmark_pack_id,
            "title": self.title,
            "output_root": self.output_root,
            "index_html_path": self.index_html_path,
            "linked_report_packs": list(self.linked_report_packs),
            "linked_html_packs": list(self.linked_html_packs),
            "sections_rendered": list(self.sections_rendered),
            "limitations": list(self.limitations),
            "blocked_interpretations": list(self.blocked_interpretations),
            "created_at": self.created_at,
            "repo_commit": self.repo_commit,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BenchmarkPackIndexV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            index_id=d.get("index_id", ""),
            benchmark_pack_id=d.get("benchmark_pack_id", ""),
            title=d.get("title", ""),
            output_root=d.get("output_root", ""),
            index_html_path=d.get("index_html_path"),
            linked_report_packs=list(d.get("linked_report_packs") or []),
            linked_html_packs=list(d.get("linked_html_packs") or []),
            sections_rendered=list(d.get("sections_rendered") or []),
            limitations=list(d.get("limitations") or []),
            blocked_interpretations=list(d.get("blocked_interpretations") or []),
            created_at=d.get("created_at", ""),
            repo_commit=d.get("repo_commit"),
            metadata=dict(d.get("metadata") or {}),
        )

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_json(cls, text: str) -> "BenchmarkPackIndexV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    def validate(self) -> list[str]:
        return validate_benchmark_pack_index(self)

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            raise BenchmarkPackIndexValidationError("; ".join(errors))
