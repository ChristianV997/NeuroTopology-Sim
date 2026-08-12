"""BenchmarkPackSpecV1 -- a curated collection of `ReportPipelineSpecV1`
entries (embedded and/or by path) to assemble into one `BenchmarkPackV1`.

Unlike `PipelineJobV1`/`BatchRunManifestV1` (execution events -- see
`job_runner.job`/`job_runner.batch_manifest`), a pack *spec* is a pure
request/definition object, mirroring `ReportPipelineSpecV1` itself:
`benchmark_pack_spec_id` is content-addressed over identity fields only,
with no `created_at` in the hash basis (or even as a field) -- building
the same spec twice is still "the same definition"; each *build*
(`job_runner.batch`'s own `batch_id`) is what carries execution-event
uniqueness.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

from benchmark_packs.validation import validate_benchmark_pack_spec

_SCHEMA_VERSION = "1"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _pipeline_spec_identities(pipeline_specs: list[dict[str, Any]], pipeline_spec_paths: list[str]) -> list[str]:
    """A stable identity handle per pipeline spec -- the embedded spec's
    own content-addressed `pipeline_id` when a dict is embedded, or the
    raw path string otherwise (mirrors `job_runner.job.compute_job_id`'s
    own `pipeline_identity` handle)."""
    identities = [str(p) for p in pipeline_spec_paths]
    identities.extend(str(d.get("pipeline_id") or "") for d in pipeline_specs)
    return sorted(identities)


def compute_benchmark_pack_spec_id(
    *, pack_name: str, pack_kind: str, pipeline_spec_identities: list[str],
    requested_outputs: list[str], output_root: str,
) -> str:
    basis = {
        "pack_name": pack_name, "pack_kind": pack_kind,
        "pipeline_spec_identities": sorted(pipeline_spec_identities or []),
        "requested_outputs": sorted(requested_outputs or []), "output_root": output_root,
    }
    return hashlib.sha256(_canonical_json(basis).encode("utf-8")).hexdigest()[:16]


class BenchmarkPackSpecValidationError(ValueError):
    """Raised when a `BenchmarkPackSpecV1` fails structural validation."""


@dataclass
class BenchmarkPackSpecV1:
    schema_version: str = _SCHEMA_VERSION
    benchmark_pack_spec_id: str = ""
    pack_name: str = ""
    pack_purpose: str = ""
    pack_kind: str = "demo_pack"
    pipeline_specs: list[dict[str, Any]] = field(default_factory=list)
    pipeline_spec_paths: list[str] = field(default_factory=list)
    requested_outputs: list[str] = field(default_factory=lambda: ["report_pack"])
    jobs_root: str = "outputs/jobs"
    output_root: str = ""
    include_html: bool = False
    run_immediately: bool = False
    max_jobs: Optional[int] = None
    limitations: list[str] = field(default_factory=list)
    provenance: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(
        cls, *, pack_name: str, output_root: str, pack_kind: str = "demo_pack",
        pipeline_specs: Optional[list[dict[str, Any]]] = None, pipeline_spec_paths: Optional[list[str]] = None,
        requested_outputs: Optional[list[str]] = None, **kwargs: Any,
    ) -> "BenchmarkPackSpecV1":
        kwargs["metadata"] = dict(kwargs.get("metadata") or {})
        pipeline_specs = [dict(d) for d in (pipeline_specs or [])]
        pipeline_spec_paths = [str(p) for p in (pipeline_spec_paths or [])]
        requested_outputs = list(requested_outputs or ["report_pack"])
        identities = _pipeline_spec_identities(pipeline_specs, pipeline_spec_paths)
        benchmark_pack_spec_id = compute_benchmark_pack_spec_id(
            pack_name=pack_name, pack_kind=pack_kind, pipeline_spec_identities=identities,
            requested_outputs=requested_outputs, output_root=output_root,
        )
        return cls(
            benchmark_pack_spec_id=benchmark_pack_spec_id, pack_name=pack_name, pack_kind=pack_kind,
            output_root=output_root, pipeline_specs=pipeline_specs, pipeline_spec_paths=pipeline_spec_paths,
            requested_outputs=requested_outputs, **kwargs,
        )

    def recompute_id(self) -> str:
        identities = _pipeline_spec_identities(self.pipeline_specs, self.pipeline_spec_paths)
        return compute_benchmark_pack_spec_id(
            pack_name=self.pack_name, pack_kind=self.pack_kind, pipeline_spec_identities=identities,
            requested_outputs=self.requested_outputs, output_root=self.output_root,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "benchmark_pack_spec_id": self.benchmark_pack_spec_id,
            "pack_name": self.pack_name,
            "pack_purpose": self.pack_purpose,
            "pack_kind": self.pack_kind,
            "pipeline_specs": [dict(d) for d in self.pipeline_specs],
            "pipeline_spec_paths": list(self.pipeline_spec_paths),
            "requested_outputs": list(self.requested_outputs),
            "jobs_root": self.jobs_root,
            "output_root": self.output_root,
            "include_html": self.include_html,
            "run_immediately": self.run_immediately,
            "max_jobs": self.max_jobs,
            "limitations": list(self.limitations),
            "provenance": self.provenance,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BenchmarkPackSpecV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            benchmark_pack_spec_id=d.get("benchmark_pack_spec_id", ""),
            pack_name=d.get("pack_name", ""),
            pack_purpose=d.get("pack_purpose", ""),
            pack_kind=d.get("pack_kind", "demo_pack"),
            pipeline_specs=[dict(x) for x in (d.get("pipeline_specs") or [])],
            pipeline_spec_paths=list(d.get("pipeline_spec_paths") or []),
            requested_outputs=list(d.get("requested_outputs") or ["report_pack"]),
            jobs_root=d.get("jobs_root", "outputs/jobs"),
            output_root=d.get("output_root", ""),
            include_html=bool(d.get("include_html", False)),
            run_immediately=bool(d.get("run_immediately", False)),
            max_jobs=d.get("max_jobs"),
            limitations=list(d.get("limitations") or []),
            provenance=d.get("provenance", ""),
            metadata=dict(d.get("metadata") or {}),
        )

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_json(cls, text: str) -> "BenchmarkPackSpecV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    def validate(self) -> list[str]:
        return validate_benchmark_pack_spec(self)

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            raise BenchmarkPackSpecValidationError("; ".join(errors))
