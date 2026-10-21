"""Versioned fixture manifest: file hashes, rubric identity, and group splits.

``load_manifest`` verifies the manifest against the files it names and against
the current rubric source. ``load_plan_records`` reads plan files only.
``load_labels`` is separate and is the only function that opens the label
file. The evaluation path never calls it.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

from tools.research_plan_quality import checks as _checks_module
from tools.research_plan_quality import models as _models_module
from tools.research_plan_quality import rubric as _rubric_module
from tools.research_plan_quality.models import RUBRIC_DIMENSIONS

from .errors import ManifestError, MalformedRecordError
from .records import PlanRecord, canonical_json, parse_json_bytes, plan_from_dict, sha256_hex
from .splits import SPLIT_ROLES, check_group_integrity

MANIFEST_SCHEMA = "NTS.ResearchPlanEvalManifest.v1"
LABELS_SCHEMA = "NTS.ResearchPlanEvalLabels.v1"
ADJUDICATION_STATUS = "synthetic_author_expectation"

_RUBRIC_SOURCE_MODULES = (_models_module, _checks_module, _rubric_module)
_RECORD_KEYS = frozenset({"fixture_id", "group_id", "split", "plan_file", "plan_sha256"})


def rubric_dimensions_sha256() -> str:
    return sha256_hex(canonical_json(list(RUBRIC_DIMENSIONS)).encode("utf-8"))


def rubric_source_sha256() -> str:
    digest = []
    for module in _RUBRIC_SOURCE_MODULES:
        source = Path(module.__file__).read_bytes()
        digest.append(f"{Path(module.__file__).name}:{sha256_hex(source)}")
    return sha256_hex("\n".join(digest).encode("utf-8"))


@dataclass(frozen=True)
class ManifestEntry:
    fixture_id: str
    group_id: str
    split: str
    plan_path: Path
    plan_sha256: str


@dataclass(frozen=True)
class Manifest:
    fixture_set_id: str
    fixture_set_version: str
    root: Path
    manifest_sha256: str
    rubric_dimensions_sha256: str
    rubric_source_sha256: str
    labels_path: Path
    labels_sha256: str
    entries: tuple[ManifestEntry, ...]


def _resolve_inside(root: Path, relative: str, what: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts or not relative:
        raise ManifestError(f"{what} must be a relative path inside the fixture root: {relative!r}")
    resolved = (root / candidate).resolve()
    if root.resolve() not in resolved.parents:
        raise ManifestError(f"{what} escapes the fixture root: {relative!r}")
    return resolved


def _read_checked(path: Path, expected_sha256: str, what: str) -> bytes:
    if not path.is_file():
        raise ManifestError(f"{what} is missing: {path.name}")
    raw = path.read_bytes()
    actual = sha256_hex(raw)
    if actual != expected_sha256:
        raise ManifestError(f"{what} hash mismatch for {path.name}: expected {expected_sha256}, got {actual}")
    return raw


def load_manifest(manifest_path: Path) -> Manifest:
    manifest_path = Path(manifest_path)
    raw = manifest_path.read_bytes()
    try:
        parsed = parse_json_bytes(raw, manifest_path.name)
    except MalformedRecordError as exc:
        raise ManifestError(str(exc)) from exc
    data = _expect_object(parsed, "manifest")
    root = manifest_path.parent

    if data.get("schema_version") != MANIFEST_SCHEMA:
        raise ManifestError(f"schema_version must be {MANIFEST_SCHEMA!r}")
    for key in ("fixture_set_id", "fixture_set_version"):
        if not isinstance(data.get(key), str) or not data[key]:
            raise ManifestError(f"manifest.{key} must be a non-empty string")
    if data.get("synthetic") is not True:
        raise ManifestError("this harness accepts only synthetic fixture sets (synthetic must be true)")

    rubric = _expect_object(data.get("rubric"), "manifest.rubric")
    if rubric.get("dimensions_sha256") != rubric_dimensions_sha256():
        raise ManifestError("rubric dimensions changed since the fixture manifest was written")
    if rubric.get("source_sha256") != rubric_source_sha256():
        raise ManifestError(
            "rubric source changed since the fixture manifest was written; "
            "labels must be re-authored and the manifest regenerated"
        )

    labels = _expect_object(data.get("labels"), "manifest.labels")
    labels_path = _resolve_inside(root, str(labels.get("file", "")), "labels.file")
    labels_sha256 = str(labels.get("sha256", ""))

    records = data.get("records")
    if not isinstance(records, list) or not records:
        raise ManifestError("manifest.records must be a non-empty list")
    entries: list[ManifestEntry] = []
    seen_ids: set[str] = set()
    for index, record in enumerate(records):
        item = _expect_object(record, f"records[{index}]")
        missing = sorted(_RECORD_KEYS - set(item))
        if missing:
            raise ManifestError(f"records[{index}] is missing keys: {missing}")
        fixture_id = str(item["fixture_id"])
        if fixture_id in seen_ids:
            raise ManifestError(f"duplicate fixture_id {fixture_id!r}")
        seen_ids.add(fixture_id)
        if item["split"] not in SPLIT_ROLES:
            raise ManifestError(f"{fixture_id}: split must be one of {list(SPLIT_ROLES)}")
        plan_path = _resolve_inside(root, str(item["plan_file"]), f"{fixture_id}.plan_file")
        _read_checked(plan_path, str(item["plan_sha256"]), f"plan file for {fixture_id}")
        entries.append(ManifestEntry(fixture_id, str(item["group_id"]), str(item["split"]), plan_path,
                                     str(item["plan_sha256"])))

    check_group_integrity((e.group_id, e.split) for e in entries)

    return Manifest(
        fixture_set_id=str(data["fixture_set_id"]),
        fixture_set_version=str(data["fixture_set_version"]),
        root=root,
        manifest_sha256=sha256_hex(raw),
        rubric_dimensions_sha256=str(rubric["dimensions_sha256"]),
        rubric_source_sha256=str(rubric["source_sha256"]),
        labels_path=labels_path,
        labels_sha256=labels_sha256,
        entries=tuple(sorted(entries, key=lambda e: e.fixture_id)),
    )


def split_definition_sha256(entries: Iterable[ManifestEntry]) -> str:
    """Digest of the split definition: each fixture's id, group, role, and plan digest.

    Plan digests are part of the definition, so editing a held-out plan changes it as well.
    """
    rows = sorted([e.fixture_id, e.group_id, e.split, e.plan_sha256] for e in entries)
    return sha256_hex(canonical_json(rows).encode("utf-8"))


def load_plan_records(manifest: Manifest, roles: Optional[Iterable[str]] = None) -> tuple[PlanRecord, ...]:
    """Plan files only, each verified against the manifest. The label file is never opened here.

    With ``roles``, plan files outside those roles are not read at all.
    """
    wanted = None if roles is None else frozenset(roles)
    records = []
    for entry in manifest.entries:
        if wanted is not None and entry.split not in wanted:
            continue
        raw = entry.plan_path.read_bytes()
        if sha256_hex(raw) != entry.plan_sha256:
            raise ManifestError(f"plan file for {entry.fixture_id} changed after the manifest was verified")
        plan = plan_from_dict(parse_json_bytes(raw, entry.plan_path.name), entry.plan_path.name)
        records.append(PlanRecord(fixture_id=entry.fixture_id, group_id=entry.group_id, split=entry.split, plan=plan))
    return tuple(records)


def load_labels(manifest: Manifest) -> dict[str, Any]:
    """Opens the label file. Only the post-hoc consistency comparison calls this."""
    raw = _read_checked(manifest.labels_path, manifest.labels_sha256, "label file")
    data = _expect_object(parse_json_bytes(raw, manifest.labels_path.name), "labels")
    if data.get("schema_version") != LABELS_SCHEMA:
        raise ManifestError(f"labels.schema_version must be {LABELS_SCHEMA!r}")
    labels = _expect_object(data.get("labels"), "labels.labels")
    for fixture_id, entry in labels.items():
        where = f"labels.labels[{fixture_id!r}]"
        entry_object = _expect_object(entry, where)
        status = entry_object.get("expected_overall_status")
        if not (isinstance(status, str) and status):
            raise ManifestError(f"{where}.expected_overall_status must be a non-empty string")
        dims = entry_object.get("expected_non_passing_dimensions")
        if not (isinstance(dims, list) and all(isinstance(dim, str) for dim in dims)):
            raise ManifestError(f"{where}.expected_non_passing_dimensions must be a list of strings")
    adjudication = _expect_object(data.get("adjudication"), "labels.adjudication")
    if adjudication.get("status") != ADJUDICATION_STATUS or adjudication.get("independent") is not False:
        raise ManifestError("labels must declare synthetic_author_expectation with independent=false")
    return data


def _expect_object(value: Any, what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ManifestError(f"{what} must be a JSON object")
    return value
