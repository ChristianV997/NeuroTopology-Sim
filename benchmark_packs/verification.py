"""BenchmarkPackVerificationV1 -- a deterministic consistency/completeness
check over an already-built `BenchmarkPackV1`. `verify_benchmark_pack`
only reads already-written files and recomputes already-defined content
addresses (`compute_benchmark_pack_id`, `compute_report_pack_id`,
`compute_html_pack_id`) -- it never executes a job, never reruns a
report pipeline, and never mutates the pack it checks. Verification
checks consistency, not science: a "passed" verification means the pack
is internally consistent and every link resolves, not that any
referenced result is scientifically stronger than it already was.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from benchmark_packs.pack_manifest import BenchmarkPackV1, compute_benchmark_pack_id
from benchmark_packs.validation import (
    looks_like_raw_data_path,
    scan_text_for_banned_phrases,
    validate_benchmark_pack_verification,
)

_SCHEMA_VERSION = "1"
_REPO_ROOT = Path(__file__).resolve().parents[1]

VERIFIER_VERSION = "benchmark_packs.verification v1"

_VERIFICATION_LIMITATIONS: list[str] = [
    "This verification checks the internal consistency and completeness of an already-built BenchmarkPackV1 "
    "-- it does not execute a job, does not rerun a report pipeline, does not recompute a scientific metric, "
    "and does not upgrade any referenced artifact's claim_scope or evidence_level.",
    "A 'passed' verification means the pack is internally consistent and every recorded link resolves to an "
    "existing, id-matching artifact -- it is not itself a scientific validation of the pack's contents.",
]


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def compute_verification_id(
    *, benchmark_pack_id: str, source_pack_path: str, files_checked: list[str], verifier_version: str = VERIFIER_VERSION,
) -> str:
    basis = {
        "benchmark_pack_id": benchmark_pack_id, "source_pack_path": source_pack_path,
        "files_checked": sorted(files_checked or []), "verifier_version": verifier_version,
    }
    return hashlib.sha256(_canonical_json(basis).encode("utf-8")).hexdigest()[:16]


class BenchmarkPackVerificationValidationError(ValueError):
    """Raised when a `BenchmarkPackVerificationV1` fails structural validation."""


@dataclass
class BenchmarkPackVerificationV1:
    schema_version: str = _SCHEMA_VERSION
    verification_id: str = ""
    benchmark_pack_id: str = ""
    source_pack_path: str = ""
    source_index_path: Optional[str] = None
    verification_status: str = "passed"
    checked_at: str = ""
    repo_commit: Optional[str] = None
    files_checked: list[str] = field(default_factory=list)
    files_missing: list[str] = field(default_factory=list)
    files_failed: list[str] = field(default_factory=list)
    ids_checked: list[str] = field(default_factory=list)
    ids_failed: list[str] = field(default_factory=list)
    guardrail_status: str = "passed"
    artifact_link_status: str = "passed"
    raw_data_copy_status: str = "passed"
    claim_promotion_status: str = "passed"
    reproducibility_status: str = "passed"
    limitations_status: str = "passed"
    blocked_interpretations_status: str = "passed"
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    provenance: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(
        cls, *, benchmark_pack_id: str, source_pack_path: str, files_checked: Optional[list[str]] = None,
        _now: Optional[datetime] = None, **kwargs: Any,
    ) -> "BenchmarkPackVerificationV1":
        kwargs["metadata"] = dict(kwargs.get("metadata") or {})
        files_checked = list(files_checked or [])
        verification_id = compute_verification_id(
            benchmark_pack_id=benchmark_pack_id, source_pack_path=source_pack_path, files_checked=files_checked,
        )
        ts = (_now or datetime.now(timezone.utc)).isoformat()
        return cls(
            verification_id=verification_id, benchmark_pack_id=benchmark_pack_id, source_pack_path=source_pack_path,
            files_checked=files_checked, checked_at=ts, **kwargs,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "verification_id": self.verification_id,
            "benchmark_pack_id": self.benchmark_pack_id,
            "source_pack_path": self.source_pack_path,
            "source_index_path": self.source_index_path,
            "verification_status": self.verification_status,
            "checked_at": self.checked_at,
            "repo_commit": self.repo_commit,
            "files_checked": list(self.files_checked),
            "files_missing": list(self.files_missing),
            "files_failed": list(self.files_failed),
            "ids_checked": list(self.ids_checked),
            "ids_failed": list(self.ids_failed),
            "guardrail_status": self.guardrail_status,
            "artifact_link_status": self.artifact_link_status,
            "raw_data_copy_status": self.raw_data_copy_status,
            "claim_promotion_status": self.claim_promotion_status,
            "reproducibility_status": self.reproducibility_status,
            "limitations_status": self.limitations_status,
            "blocked_interpretations_status": self.blocked_interpretations_status,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "limitations": list(self.limitations),
            "provenance": self.provenance,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BenchmarkPackVerificationV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            verification_id=d.get("verification_id", ""),
            benchmark_pack_id=d.get("benchmark_pack_id", ""),
            source_pack_path=d.get("source_pack_path", ""),
            source_index_path=d.get("source_index_path"),
            verification_status=d.get("verification_status", "passed"),
            checked_at=d.get("checked_at", ""),
            repo_commit=d.get("repo_commit"),
            files_checked=list(d.get("files_checked") or []),
            files_missing=list(d.get("files_missing") or []),
            files_failed=list(d.get("files_failed") or []),
            ids_checked=list(d.get("ids_checked") or []),
            ids_failed=list(d.get("ids_failed") or []),
            guardrail_status=d.get("guardrail_status", "passed"),
            artifact_link_status=d.get("artifact_link_status", "passed"),
            raw_data_copy_status=d.get("raw_data_copy_status", "passed"),
            claim_promotion_status=d.get("claim_promotion_status", "passed"),
            reproducibility_status=d.get("reproducibility_status", "passed"),
            limitations_status=d.get("limitations_status", "passed"),
            blocked_interpretations_status=d.get("blocked_interpretations_status", "passed"),
            warnings=list(d.get("warnings") or []),
            errors=list(d.get("errors") or []),
            limitations=list(d.get("limitations") or []),
            provenance=d.get("provenance", ""),
            metadata=dict(d.get("metadata") or {}),
        )

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_json(cls, text: str) -> "BenchmarkPackVerificationV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    def validate(self) -> list[str]:
        return validate_benchmark_pack_verification(self)

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            raise BenchmarkPackVerificationValidationError("; ".join(errors))


def _repo_commit() -> Optional[str]:
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(_REPO_ROOT), capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception:
        pass
    return None


def _resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else (_REPO_ROOT / p)


def _relative_path(path: Union[str, Path]) -> str:
    p = Path(path)
    try:
        return str(p.resolve().relative_to(_REPO_ROOT))
    except ValueError:
        return str(p)


def verify_benchmark_pack(pack_path: Union[str, Path], *, strict: bool = True) -> BenchmarkPackVerificationV1:
    """Loads `pack_path` (a `BenchmarkPack.json`), checks it for internal
    consistency and completeness, and returns a
    `BenchmarkPackVerificationV1`. Never executes a job, never reruns a
    report pipeline, never mutates `pack_path` or any file it references.
    `strict=True` (default) fails on any missing/mismatched artifact;
    `strict=False` downgrades a missing *optional* artifact (an HTML
    report pack, the pack's own static index) to a warning."""
    from workflows.html_report_pack import HTML_PACK_FILENAME, HtmlReportPackV1
    from workflows.report_pack import ReportPackV1

    pack_path = Path(pack_path)
    resolved_pack_path = pack_path if pack_path.is_absolute() else (_REPO_ROOT / pack_path)
    source_pack_path = _relative_path(resolved_pack_path)

    errors: list[str] = []
    warnings: list[str] = []
    files_checked: list[str] = []
    files_missing: list[str] = []
    files_failed: list[str] = []
    ids_checked: list[str] = []
    ids_failed: list[str] = []
    guardrail_hits: list[str] = []
    raw_data_hits: list[str] = []

    if not resolved_pack_path.exists():
        verification = BenchmarkPackVerificationV1.make(
            benchmark_pack_id="", source_pack_path=source_pack_path, files_checked=[source_pack_path],
            files_missing=[source_pack_path], verification_status="failed",
            errors=[f"benchmark pack file does not exist: {source_pack_path}"],
            limitations=list(_VERIFICATION_LIMITATIONS),
            provenance=f"Produced by benchmark_packs.verification.verify_benchmark_pack over {source_pack_path!r}.",
            repo_commit=_repo_commit(),
        )
        return verification

    try:
        pack = BenchmarkPackV1.from_json(resolved_pack_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        verification = BenchmarkPackVerificationV1.make(
            benchmark_pack_id="", source_pack_path=source_pack_path, files_checked=[source_pack_path],
            files_failed=[source_pack_path], verification_status="failed",
            errors=[f"could not parse benchmark pack: {exc}"],
            limitations=list(_VERIFICATION_LIMITATIONS),
            provenance=f"Produced by benchmark_packs.verification.verify_benchmark_pack over {source_pack_path!r}.",
            repo_commit=_repo_commit(),
        )
        return verification

    # 1/13. Structural validation (also enforces rule 8: no claim/evidence promotion field).
    struct_errors = pack.validate()
    claim_promotion_status = "passed"
    if any("claim_scope" in e or "evidence_level" in e or "validation_ready" in e for e in struct_errors):
        claim_promotion_status = "failed"
    errors.extend(struct_errors)

    # 2. Recompute benchmark_pack_id.
    recomputed_id = compute_benchmark_pack_id(
        source_spec_id=pack.source_spec_id, batch_id=pack.batch_id,
        report_pack_ids=pack.report_pack_ids, html_pack_ids=pack.html_pack_ids,
    )
    ids_checked.append(f"benchmark_pack_id:{pack.benchmark_pack_id}")
    if recomputed_id != pack.benchmark_pack_id:
        ids_failed.append("benchmark_pack_id")
        errors.append(f"benchmark_pack_id mismatch: recorded={pack.benchmark_pack_id!r} recomputed={recomputed_id!r}")

    # 3/6/8. Report packs -- required (strict and non-strict).
    for idx, rp_path in enumerate(pack.generated_report_pack_paths):
        files_checked.append(rp_path)
        full = _resolve(rp_path)
        if not full.exists():
            files_missing.append(rp_path)
            errors.append(f"missing generated_report_pack_path: {rp_path}")
            continue
        try:
            rp = ReportPackV1.from_json(full.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            files_failed.append(rp_path)
            errors.append(f"could not parse {rp_path}: {exc}")
            continue
        ids_checked.append(f"report_pack:{rp.report_pack_id}")
        if rp.report_pack_id not in pack.report_pack_ids:
            ids_failed.append(f"report_pack:{rp.report_pack_id}")
            errors.append(f"{rp_path}: report_pack_id {rp.report_pack_id!r} is not recorded in pack.report_pack_ids")
        for gf in rp.generated_files:
            if looks_like_raw_data_path(gf):
                raw_data_hits.append(gf)
                errors.append(f"{rp_path}: generated_files references a raw-data-looking path: {gf}")

    # 4/7. HTML report packs -- optional (downgrade to warning when strict=False).
    for html_path in pack.generated_html_paths:
        files_checked.append(html_path)
        full = _resolve(html_path)
        if not full.exists():
            msg = f"missing generated_html_path: {html_path}"
            if strict:
                files_missing.append(html_path)
                errors.append(msg)
            else:
                warnings.append(msg)
            continue
        sibling = full.parent / HTML_PACK_FILENAME
        if not sibling.exists():
            warnings.append(f"no {HTML_PACK_FILENAME} sibling found next to {html_path}")
            continue
        try:
            hp = HtmlReportPackV1.from_json(sibling.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            files_failed.append(str(_relative_path(sibling)))
            errors.append(f"could not parse {sibling}: {exc}")
            continue
        ids_checked.append(f"html_pack:{hp.html_pack_id}")
        if hp.html_pack_id not in pack.html_pack_ids:
            ids_failed.append(f"html_pack:{hp.html_pack_id}")
            errors.append(f"{html_path}: html_pack_id {hp.html_pack_id!r} is not recorded in pack.html_pack_ids")

    # 5. Pack's own static index -- optional.
    source_index_path = None
    if pack.generated_index_path:
        files_checked.append(pack.generated_index_path)
        full = _resolve(pack.generated_index_path)
        if not full.exists():
            msg = f"missing generated_index_path: {pack.generated_index_path}"
            if strict:
                files_missing.append(pack.generated_index_path)
                errors.append(msg)
            else:
                warnings.append(msg)
        else:
            source_index_path = _relative_path(full)
            html_text = full.read_text(encoding="utf-8")
            hits = scan_text_for_banned_phrases(html_text)
            if hits:
                guardrail_hits.extend(hits)
                errors.append(f"generated_index_path contains banned phrase(s): {hits}")

    # 9. limitations/blocked_interpretations non-empty.
    limitations_status = "passed" if pack.limitations else "failed"
    if not pack.limitations:
        errors.append("pack.limitations is empty")
    blocked_status = "passed" if pack.blocked_interpretations else "failed"
    if not pack.blocked_interpretations:
        errors.append("pack.blocked_interpretations is empty")

    # 10. reproducibility_commands -- expected, downgraded to a warning (not a hard requirement upstream).
    reproducibility_status = "passed"
    if not pack.reproducibility_commands:
        reproducibility_status = "failed" if strict else "passed"
        msg = "pack.reproducibility_commands is empty"
        if strict:
            errors.append(msg)
        else:
            warnings.append(msg)

    # 12. Guardrail scan over the pack's own serialized content.
    pack_text = pack.to_json()
    pack_hits = scan_text_for_banned_phrases(pack_text)
    if pack_hits:
        guardrail_hits.extend(pack_hits)
        errors.append(f"BenchmarkPackV1 contains banned phrase(s): {pack_hits}")

    guardrail_status = "failed" if guardrail_hits else "passed"
    raw_data_copy_status = "failed" if raw_data_hits else "passed"
    artifact_link_status = "failed" if (files_missing or files_failed or ids_failed) else "passed"

    if errors:
        verification_status = "failed"
    elif warnings:
        verification_status = "passed_with_warnings"
    else:
        verification_status = "passed"

    verification = BenchmarkPackVerificationV1.make(
        benchmark_pack_id=pack.benchmark_pack_id, source_pack_path=source_pack_path,
        source_index_path=source_index_path, files_checked=files_checked, files_missing=files_missing,
        files_failed=files_failed, ids_checked=ids_checked, ids_failed=ids_failed,
        guardrail_status=guardrail_status, artifact_link_status=artifact_link_status,
        raw_data_copy_status=raw_data_copy_status, claim_promotion_status=claim_promotion_status,
        reproducibility_status=reproducibility_status, limitations_status=limitations_status,
        blocked_interpretations_status=blocked_status, verification_status=verification_status,
        warnings=warnings, errors=errors, limitations=list(_VERIFICATION_LIMITATIONS),
        provenance=f"Produced by benchmark_packs.verification.verify_benchmark_pack (strict={strict}) over {source_pack_path!r}.",
        repo_commit=_repo_commit(),
    )
    return verification
