"""BenchmarkGalleryV1 -- a deterministic index over multiple verified
`BenchmarkPackV1` artifacts. `build_benchmark_gallery` only reads
already-built `BenchmarkPack.json` files, verifies each one via
`benchmark_packs.verification.verify_benchmark_pack` (unmodified), and
assembles a gallery -- it never executes a job, never reruns a report
pipeline, and never mutates a pack it references.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from benchmark_packs.validation import validate_benchmark_gallery

_SCHEMA_VERSION = "1"
_REPO_ROOT = Path(__file__).resolve().parents[1]

GALLERY_FILENAME = "BenchmarkGallery.json"
VERIFICATIONS_SUBDIR = "verifications"

_GALLERY_LIMITATIONS: list[str] = [
    "This gallery only indexes already-built BenchmarkPackV1 artifacts, verified by "
    "benchmark_packs.verification.verify_benchmark_pack -- it contains no scientific logic of its own and "
    "executes no job or report pipeline.",
    "A pack listed here as verified is internally consistent, not scientifically stronger than the "
    "already-governed report packs it references.",
]


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


def _relative_path(path: Union[str, Path]) -> str:
    p = Path(path)
    try:
        return str(p.resolve().relative_to(_REPO_ROOT))
    except ValueError:
        return str(p)


def compute_gallery_id(*, gallery_name: str, benchmark_pack_paths: list[str], verification_ids: list[str]) -> str:
    basis = {
        "gallery_name": gallery_name, "benchmark_pack_paths": sorted(benchmark_pack_paths or []),
        "verification_ids": sorted(verification_ids or []),
    }
    return hashlib.sha256(_canonical_json(basis).encode("utf-8")).hexdigest()[:16]


def gallery_blocked_interpretations_template() -> list[str]:
    """Mirrors `benchmark_packs.pack_manifest.benchmark_pack_blocked_interpretations_template`,
    extended for a multi-pack gallery."""
    return [
        "This gallery does not support a clinical claim.",
        "This gallery does not support a diagnostic claim.",
        "This gallery does not support a treatment claim.",
        "This gallery does not support a claim that any listed pack or referenced artifact is a validated "
        "consciousness biomarker.",
        "This gallery does not support a claim of spiritual/meditative attainment.",
        "This gallery does not support a mechanistic-causal claim.",
        "This gallery is not itself clinical evidence -- it is a curated, verified index of already-governed "
        "benchmark packs.",
        "This gallery does not promote the claim_scope_ceiling or evidence_level_ceiling of any listed pack "
        "or its referenced report packs.",
        "Listing a pack in this gallery does not itself constitute additional evidence beyond what that pack "
        "already carries.",
        "A 'verified' status on a pack in this gallery means internal consistency (files/ids resolve, "
        "guardrail-clean) -- it is not a scientific validation of that pack's contents.",
    ]


class BenchmarkGalleryValidationError(ValueError):
    """Raised when a `BenchmarkGalleryV1` fails structural validation."""


@dataclass
class BenchmarkGalleryV1:
    schema_version: str = _SCHEMA_VERSION
    gallery_id: str = ""
    gallery_name: str = ""
    source_roots: list[str] = field(default_factory=list)
    benchmark_pack_paths: list[str] = field(default_factory=list)
    verification_paths: list[str] = field(default_factory=list)
    verified_pack_ids: list[str] = field(default_factory=list)
    failed_pack_ids: list[str] = field(default_factory=list)
    pack_summaries: list[dict[str, Any]] = field(default_factory=list)
    dataset_ids: list[str] = field(default_factory=list)
    modalities: list[str] = field(default_factory=list)
    input_modes: list[str] = field(default_factory=list)
    html_index_paths: list[str] = field(default_factory=list)
    report_pack_paths: list[str] = field(default_factory=list)
    generated_gallery_index_path: Optional[str] = None
    created_at: str = ""
    repo_commit: Optional[str] = None
    limitations: list[str] = field(default_factory=list)
    blocked_interpretations: list[str] = field(default_factory=gallery_blocked_interpretations_template)
    provenance: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(
        cls, *, gallery_name: str, benchmark_pack_paths: Optional[list[str]] = None,
        verification_ids: Optional[list[str]] = None, _now: Optional[datetime] = None, **kwargs: Any,
    ) -> "BenchmarkGalleryV1":
        kwargs["metadata"] = dict(kwargs.get("metadata") or {})
        benchmark_pack_paths = list(benchmark_pack_paths or [])
        gallery_id = compute_gallery_id(
            gallery_name=gallery_name, benchmark_pack_paths=benchmark_pack_paths,
            verification_ids=list(verification_ids or []),
        )
        ts = (_now or datetime.now(timezone.utc)).isoformat()
        return cls(
            gallery_id=gallery_id, gallery_name=gallery_name, benchmark_pack_paths=benchmark_pack_paths,
            created_at=ts, repo_commit=kwargs.pop("repo_commit", None) or _repo_commit(), **kwargs,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "gallery_id": self.gallery_id,
            "gallery_name": self.gallery_name,
            "source_roots": list(self.source_roots),
            "benchmark_pack_paths": list(self.benchmark_pack_paths),
            "verification_paths": list(self.verification_paths),
            "verified_pack_ids": list(self.verified_pack_ids),
            "failed_pack_ids": list(self.failed_pack_ids),
            "pack_summaries": [dict(s) for s in self.pack_summaries],
            "dataset_ids": list(self.dataset_ids),
            "modalities": list(self.modalities),
            "input_modes": list(self.input_modes),
            "html_index_paths": list(self.html_index_paths),
            "report_pack_paths": list(self.report_pack_paths),
            "generated_gallery_index_path": self.generated_gallery_index_path,
            "created_at": self.created_at,
            "repo_commit": self.repo_commit,
            "limitations": list(self.limitations),
            "blocked_interpretations": list(self.blocked_interpretations),
            "provenance": self.provenance,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BenchmarkGalleryV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            gallery_id=d.get("gallery_id", ""),
            gallery_name=d.get("gallery_name", ""),
            source_roots=list(d.get("source_roots") or []),
            benchmark_pack_paths=list(d.get("benchmark_pack_paths") or []),
            verification_paths=list(d.get("verification_paths") or []),
            verified_pack_ids=list(d.get("verified_pack_ids") or []),
            failed_pack_ids=list(d.get("failed_pack_ids") or []),
            pack_summaries=[dict(s) for s in (d.get("pack_summaries") or [])],
            dataset_ids=list(d.get("dataset_ids") or []),
            modalities=list(d.get("modalities") or []),
            input_modes=list(d.get("input_modes") or []),
            html_index_paths=list(d.get("html_index_paths") or []),
            report_pack_paths=list(d.get("report_pack_paths") or []),
            generated_gallery_index_path=d.get("generated_gallery_index_path"),
            created_at=d.get("created_at", ""),
            repo_commit=d.get("repo_commit"),
            limitations=list(d.get("limitations") or []),
            blocked_interpretations=list(d.get("blocked_interpretations") or []),
            provenance=d.get("provenance", ""),
            metadata=dict(d.get("metadata") or {}),
        )

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_json(cls, text: str) -> "BenchmarkGalleryV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    def validate(self) -> list[str]:
        return validate_benchmark_gallery(self)

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            raise BenchmarkGalleryValidationError("; ".join(errors))


def discover_benchmark_pack_paths(root: Union[str, Path]) -> list[str]:
    """Globs `root` for `BenchmarkPack.json` files, sorted for determinism.
    Never reads or validates their content -- pure filesystem discovery."""
    root_path = Path(root)
    if not root_path.is_absolute():
        root_path = _REPO_ROOT / root_path
    if not root_path.exists():
        return []
    return sorted(_relative_path(p) for p in root_path.glob("**/BenchmarkPack.json"))


def build_benchmark_gallery(
    pack_paths: list[str], output_root: Union[str, Path], *,
    gallery_name: str = "NeuroTopology Benchmark Gallery", verify: bool = True, strict: bool = True,
    source_roots: Optional[list[str]] = None,
) -> BenchmarkGalleryV1:
    """1. Validates `output_root`. 2. Verifies each pack in `pack_paths`
    via `verify_benchmark_pack` (unless `verify=False`). 3. Only packs
    whose verification is `passed`/`passed_with_warnings` are counted in
    `verified_pack_ids`; every other pack (including one that failed to
    load) goes into `failed_pack_ids`. 4. Aggregates dataset/modality/
    input-mode coverage and per-pack summaries from verified packs only.
    5. Writes `BenchmarkGallery.json` under `output_root`. Never copies a
    raw data file, never mutates an input pack."""
    from benchmark_packs.pack_manifest import BenchmarkPackV1
    from benchmark_packs.validation import BenchmarkPackStoreError, _validate_repo_relative_root
    from benchmark_packs.verification import verify_benchmark_pack

    output_root_errors = _validate_repo_relative_root(str(output_root), "output_root")
    if output_root_errors:
        raise BenchmarkPackStoreError("; ".join(output_root_errors))

    resolved_output_root = Path(output_root)
    if not resolved_output_root.is_absolute():
        resolved_output_root = _REPO_ROOT / resolved_output_root

    verification_paths: list[str] = []
    verification_ids: list[str] = []
    verified_pack_ids: list[str] = []
    failed_pack_ids: list[str] = []
    pack_summaries: list[dict[str, Any]] = []
    dataset_ids: set = set()
    modalities: set = set()
    input_modes: set = set()
    html_index_paths: list[str] = []
    report_pack_paths: list[str] = []

    for pack_path in pack_paths:
        if verify:
            verification = verify_benchmark_pack(pack_path, strict=strict)
        else:
            verification = None

        try:
            resolved_pack_path = Path(pack_path)
            if not resolved_pack_path.is_absolute():
                resolved_pack_path = _REPO_ROOT / resolved_pack_path
            pack = BenchmarkPackV1.from_json(resolved_pack_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            if verification is not None:
                failed_pack_ids.append(verification.benchmark_pack_id or pack_path)
            continue

        if verification is not None:
            verification_dir = resolved_output_root / VERIFICATIONS_SUBDIR
            verification_path = verification_dir / f"{pack.benchmark_pack_id}.json"
            verification.write_json(verification_path)
            verification_paths.append(_relative_path(verification_path))
            verification_ids.append(verification.verification_id)

            if verification.verification_status in ("passed", "passed_with_warnings"):
                verified_pack_ids.append(pack.benchmark_pack_id)
            else:
                failed_pack_ids.append(pack.benchmark_pack_id)
                continue
        else:
            verified_pack_ids.append(pack.benchmark_pack_id)

        dataset_ids.update(pack.dataset_ids)
        modalities.update(pack.modalities)
        input_modes.update(pack.input_modes)
        html_index_paths.extend(pack.generated_html_paths)
        report_pack_paths.extend(pack.generated_report_pack_paths)

        pack_summaries.append({
            "benchmark_pack_id": pack.benchmark_pack_id,
            "pack_name": pack.pack_name,
            "pack_kind": pack.pack_kind,
            "pack_purpose": pack.pack_purpose,
            "dataset_ids": list(pack.dataset_ids),
            "modalities": list(pack.modalities),
            "input_modes": list(pack.input_modes),
            "report_pack_count": len(pack.report_pack_ids),
            "html_pack_count": len(pack.html_pack_ids),
            "verification_status": verification.verification_status if verification is not None else "not_verified",
            "limitations_count": len(pack.limitations),
            "generated_index_path": pack.generated_index_path,
            "source_pack_path": _relative_path(resolved_pack_path),
        })

    gallery = BenchmarkGalleryV1.make(
        gallery_name=gallery_name, benchmark_pack_paths=[str(p) for p in pack_paths],
        verification_ids=verification_ids, source_roots=list(source_roots or []),
        verification_paths=verification_paths, verified_pack_ids=verified_pack_ids,
        failed_pack_ids=failed_pack_ids, pack_summaries=pack_summaries,
        dataset_ids=sorted(dataset_ids), modalities=sorted(modalities), input_modes=sorted(input_modes),
        html_index_paths=html_index_paths, report_pack_paths=report_pack_paths,
        limitations=list(_GALLERY_LIMITATIONS),
        provenance=f"Produced by benchmark_packs.gallery.build_benchmark_gallery over {len(pack_paths)} pack(s).",
    )
    gallery.validate_or_raise()

    from benchmark_packs.gallery_renderer import render_benchmark_gallery_index

    gallery_index = render_benchmark_gallery_index(gallery, resolved_output_root)
    gallery.generated_gallery_index_path = gallery_index.index_html_path

    gallery.validate_or_raise()
    gallery.write_json(resolved_output_root / GALLERY_FILENAME)
    return gallery
