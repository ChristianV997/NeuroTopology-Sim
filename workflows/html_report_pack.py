"""HtmlReportPackV1 -- a deterministic, static HTML presentation of an
already-built `ReportPackV1` (and, if present, its linked
`EvidenceReportV1`/`EvidenceBundleV1` artifacts).

This module renders, it does not analyze: every number shown in the
generated `index.html` was already computed by `evidence.builder`/
`reports.evidence_report`/`workflows.report_pipeline` before this module
runs. See docs/html_report_pack_renderer.md.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from workflows.html_validation import (
    HtmlReportPackError,
    HtmlReportPackValidationError,
    TEMPLATE_VERSION,
    scan_html_for_banned_phrases,
    validate_html_report_pack,
    validate_source_artifacts_exist,
)

_SCHEMA_VERSION = "1"
_REPO_ROOT = Path(__file__).resolve().parents[1]

# Only small, already-governed JSON/Markdown artifacts are ever copied --
# never a raw data file. This is a defensive ceiling, not an expectation
# any real artifact should approach.
_MAX_COPIED_ARTIFACT_BYTES = 5_000_000

HTML_PACK_FILENAME = "HtmlReportPack.json"
INDEX_FILENAME = "index.html"
ARTIFACTS_SUBDIR = "artifacts"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def compute_html_pack_id(
    *, report_pack_id: str, dataset_id: str, input_mode: str,
    source_evidence_report_paths: list[str], template_version: str = TEMPLATE_VERSION,
) -> str:
    """Stable sha256[:16] over the html pack's identity fields only --
    excludes `created_at`, `title`, `limitations`, and every other mutable/
    free-text field. `template_version` participates so a future renderer
    template change deliberately yields a new id rather than silently
    overwriting a pack built with different rendering logic (mirrors
    `phase_space.coordinate.ESTIMATOR_VERSION`'s role in `coordinate_id`)."""
    basis = {
        "report_pack_id": report_pack_id,
        "dataset_id": dataset_id,
        "input_mode": input_mode,
        "source_evidence_report_paths": sorted(source_evidence_report_paths or []),
        "template_version": template_version,
    }
    return hashlib.sha256(_canonical_json(basis).encode("utf-8")).hexdigest()[:16]


def _repo_commit() -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(_REPO_ROOT), capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception:
        pass
    return None


def _relative_path(path: Union[str, Path]) -> str:
    p = Path(path)
    try:
        return str(p.resolve().relative_to(_REPO_ROOT))
    except ValueError:
        return str(p)


@dataclass
class HtmlReportPackV1:
    schema_version: str = _SCHEMA_VERSION
    html_pack_id: str = ""
    report_pack_id: str = ""
    pipeline_run_id: str = ""
    dataset_id: str = ""
    modality: str = ""
    input_mode: str = ""
    title: str = ""
    source_report_pack_path: str = ""
    source_pipeline_manifest_path: Optional[str] = None
    source_evidence_report_paths: list[str] = field(default_factory=list)
    source_evidence_bundle_paths: list[str] = field(default_factory=list)
    output_root: str = ""
    index_html_path: str = ""
    copied_artifact_paths: list[str] = field(default_factory=list)
    rendered_sections: list[str] = field(default_factory=list)
    validation_summary: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    blocked_interpretations: list[str] = field(default_factory=list)
    reproducibility_commands: list[str] = field(default_factory=list)
    created_at: str = ""
    repo_commit: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(
        cls,
        *,
        report_pack_id: str,
        dataset_id: str,
        input_mode: str,
        source_evidence_report_paths: Optional[list[str]] = None,
        _now: Optional[datetime] = None,
        **kwargs: Any,
    ) -> "HtmlReportPackV1":
        source_evidence_report_paths = list(source_evidence_report_paths or [])
        html_pack_id = compute_html_pack_id(
            report_pack_id=report_pack_id, dataset_id=dataset_id, input_mode=input_mode,
            source_evidence_report_paths=source_evidence_report_paths,
        )
        ts = (_now or datetime.now(timezone.utc)).isoformat()
        return cls(
            html_pack_id=html_pack_id, report_pack_id=report_pack_id, dataset_id=dataset_id,
            input_mode=input_mode, source_evidence_report_paths=source_evidence_report_paths,
            created_at=ts, **kwargs,
        )

    def recompute_id(self) -> str:
        return compute_html_pack_id(
            report_pack_id=self.report_pack_id, dataset_id=self.dataset_id, input_mode=self.input_mode,
            source_evidence_report_paths=self.source_evidence_report_paths,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "html_pack_id": self.html_pack_id,
            "report_pack_id": self.report_pack_id,
            "pipeline_run_id": self.pipeline_run_id,
            "dataset_id": self.dataset_id,
            "modality": self.modality,
            "input_mode": self.input_mode,
            "title": self.title,
            "source_report_pack_path": self.source_report_pack_path,
            "source_pipeline_manifest_path": self.source_pipeline_manifest_path,
            "source_evidence_report_paths": list(self.source_evidence_report_paths),
            "source_evidence_bundle_paths": list(self.source_evidence_bundle_paths),
            "output_root": self.output_root,
            "index_html_path": self.index_html_path,
            "copied_artifact_paths": list(self.copied_artifact_paths),
            "rendered_sections": list(self.rendered_sections),
            "validation_summary": dict(self.validation_summary or {}),
            "limitations": list(self.limitations),
            "blocked_interpretations": list(self.blocked_interpretations),
            "reproducibility_commands": list(self.reproducibility_commands),
            "created_at": self.created_at,
            "repo_commit": self.repo_commit,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "HtmlReportPackV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            html_pack_id=d.get("html_pack_id", ""),
            report_pack_id=d.get("report_pack_id", ""),
            pipeline_run_id=d.get("pipeline_run_id", ""),
            dataset_id=d.get("dataset_id", ""),
            modality=d.get("modality", ""),
            input_mode=d.get("input_mode", ""),
            title=d.get("title", ""),
            source_report_pack_path=d.get("source_report_pack_path", ""),
            source_pipeline_manifest_path=d.get("source_pipeline_manifest_path"),
            source_evidence_report_paths=list(d.get("source_evidence_report_paths") or []),
            source_evidence_bundle_paths=list(d.get("source_evidence_bundle_paths") or []),
            output_root=d.get("output_root", ""),
            index_html_path=d.get("index_html_path", ""),
            copied_artifact_paths=list(d.get("copied_artifact_paths") or []),
            rendered_sections=list(d.get("rendered_sections") or []),
            validation_summary=dict(d.get("validation_summary") or {}),
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
    def from_json(cls, text: str) -> "HtmlReportPackV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    def validate(self) -> list[str]:
        return validate_html_report_pack(self)

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            raise HtmlReportPackValidationError("; ".join(errors))


# ── rendering orchestration ────────────────────────────────────────────────


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _copy_artifact(src: Path, dest_dir: Path, *, warnings: list[str]) -> Optional[str]:
    if not src.exists():
        return None
    if src.stat().st_size > _MAX_COPIED_ARTIFACT_BYTES:
        warnings.append(f"skipped copying oversized artifact (> {_MAX_COPIED_ARTIFACT_BYTES} bytes): {src}")
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    shutil.copyfile(src, dest)
    return _relative_path(dest)


def render_html_report_pack(
    *,
    report_pack_path: Union[str, Path],
    out_dir: Union[str, Path],
    pipeline_manifest_path: Optional[Union[str, Path]] = None,
    title: Optional[str] = None,
    copy_artifacts: bool = True,
) -> HtmlReportPackV1:
    """Reads an already-built `ReportPackV1` (and, optionally, a
    `ReportPipelineRunManifestV1`) from disk, renders a static
    `index.html`, and writes `HtmlReportPack.json` alongside it.

    Fails closed (`HtmlReportPackError`) if `report_pack_path` does not
    exist, if any *declared* linked evidence-report/bundle path does not
    exist, or if the rendered HTML trips the banned-phrase scan --
    matching every other adapter/recipe/runner in this repository's
    "validate before write" discipline."""
    from dataset_acquisition.store import validate_target_root
    from workflows.html_renderer import render_index_html
    from workflows.report_pack import ReportPackV1

    report_pack_path = Path(report_pack_path)
    if not report_pack_path.is_absolute():
        report_pack_path = _REPO_ROOT / report_pack_path
    if not report_pack_path.exists():
        raise HtmlReportPackError(f"source_report_pack_path does not exist: {report_pack_path}")

    pack = ReportPackV1.from_json(report_pack_path.read_text(encoding="utf-8"))
    pack_errors = pack.validate()
    if pack_errors:
        raise HtmlReportPackError(f"source ReportPack failed validation: {'; '.join(pack_errors)}")

    artifact_manifest = pack.artifact_manifest or {}
    source_evidence_report_paths = list(artifact_manifest.get("evidence_report_paths") or [])
    source_evidence_bundle_paths = list(artifact_manifest.get("evidence_bundle_paths") or [])

    existence_errors = validate_source_artifacts_exist(
        source_report_pack_path=report_pack_path,
        source_evidence_report_paths=source_evidence_report_paths,
        source_evidence_bundle_paths=source_evidence_bundle_paths,
        repo_root=_REPO_ROOT,
    )
    if existence_errors:
        raise HtmlReportPackError(f"linked artifact(s) missing: {'; '.join(existence_errors)}")

    resolved_out = validate_target_root(out_dir)
    resolved_out.mkdir(parents=True, exist_ok=True)
    artifacts_dir = resolved_out / ARTIFACTS_SUBDIR

    pipeline_manifest: Optional[dict[str, Any]] = None
    pipeline_manifest_rel: Optional[str] = None
    if pipeline_manifest_path is not None:
        pm_path = Path(pipeline_manifest_path)
        if not pm_path.is_absolute():
            pm_path = _REPO_ROOT / pm_path
        if not pm_path.exists():
            raise HtmlReportPackError(f"pipeline_manifest_path does not exist: {pipeline_manifest_path}")
        pipeline_manifest = _load_json(pm_path)
        pipeline_manifest_rel = _relative_path(pm_path)

    evidence_report_docs: list[dict[str, Any]] = []
    evidence_report_md_texts: list[str] = []
    for rel in source_evidence_report_paths:
        p = Path(rel)
        if not p.is_absolute():
            p = _REPO_ROOT / p
        if p.suffix == ".json":
            evidence_report_docs.append(_load_json(p))
        elif p.suffix == ".md":
            evidence_report_md_texts.append(p.read_text(encoding="utf-8"))

    evidence_bundle_docs: list[dict[str, Any]] = []
    for rel in source_evidence_bundle_paths:
        p = Path(rel)
        if not p.is_absolute():
            p = _REPO_ROOT / p
        evidence_bundle_docs.append(_load_json(p))

    warnings: list[str] = []
    copied_artifact_paths: list[str] = []
    if copy_artifacts:
        copied_report_pack = _copy_artifact(report_pack_path, artifacts_dir, warnings=warnings)
        if copied_report_pack:
            copied_artifact_paths.append(copied_report_pack)
        if pipeline_manifest_path is not None:
            pm_path = Path(pipeline_manifest_path)
            if not pm_path.is_absolute():
                pm_path = _REPO_ROOT / pm_path
            copied = _copy_artifact(pm_path, artifacts_dir, warnings=warnings)
            if copied:
                copied_artifact_paths.append(copied)
        for rel in source_evidence_report_paths + source_evidence_bundle_paths:
            p = Path(rel)
            if not p.is_absolute():
                p = _REPO_ROOT / p
            copied = _copy_artifact(p, artifacts_dir, warnings=warnings)
            if copied:
                copied_artifact_paths.append(copied)

    html_pack = HtmlReportPackV1.make(
        report_pack_id=pack.report_pack_id, dataset_id=pack.dataset_id, input_mode=pack.input_mode,
        source_evidence_report_paths=source_evidence_report_paths,
        pipeline_run_id=pack.pipeline_run_id, modality=pack.modality,
        title=title or f"Report Pack -- {pack.dataset_id} ({pack.input_mode})",
        source_report_pack_path=_relative_path(report_pack_path),
        source_pipeline_manifest_path=pipeline_manifest_rel,
        source_evidence_bundle_paths=source_evidence_bundle_paths,
        output_root=str(out_dir),
        copied_artifact_paths=copied_artifact_paths,
        limitations=list(pack.limitations) + [
            "This HTML page is a deterministic, static rendering of an existing ReportPackV1 -- it "
            "recomputes nothing and reinterprets no science; every number shown already existed in the "
            "referenced ReportPack.json/EvidenceReport.json/EvidenceBundle.json files.",
            "This page was generated without any LLM call.",
        ],
        blocked_interpretations=list(pack.blocked_interpretations),
        reproducibility_commands=list(pack.reproducibility_commands) + [
            f"python -m workflows.export_html_report_pack --report-pack {_relative_path(report_pack_path)} --out {out_dir}"
        ],
        repo_commit=_repo_commit(),
    )

    html_text, rendered_sections = render_index_html(
        html_pack=html_pack, report_pack=pack, pipeline_manifest=pipeline_manifest,
        evidence_report_docs=evidence_report_docs, evidence_bundle_docs=evidence_bundle_docs,
        evidence_report_md_texts=evidence_report_md_texts,
        copied_artifact_paths=copied_artifact_paths,
        source_evidence_report_paths=source_evidence_report_paths,
        source_evidence_bundle_paths=source_evidence_bundle_paths,
    )
    html_pack.rendered_sections = rendered_sections

    banned_hits = scan_html_for_banned_phrases(html_text)
    if banned_hits:
        raise HtmlReportPackError(f"rendered HTML contains banned phrase(s), refusing to write: {banned_hits}")

    index_path = resolved_out / INDEX_FILENAME
    index_path.write_text(html_text, encoding="utf-8")
    html_pack.index_html_path = _relative_path(index_path)
    html_pack.validation_summary = {
        "source_report_pack_valid": True,
        "banned_phrase_scan_hits": 0,
        "copied_artifact_count": len(copied_artifact_paths),
        "warnings": warnings,
    }

    html_pack.validate_or_raise()
    html_pack.write_json(resolved_out / HTML_PACK_FILENAME)
    return html_pack
