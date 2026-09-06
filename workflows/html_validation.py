"""Structural validation and banned-phrase scanning for `HtmlReportPackV1`.

Mirrors `workflows.validation`'s split: pure structural checks here
(`validate_html_report_pack`, no filesystem access), a separate
filesystem-touching existence check (`validate_source_artifacts_exist`)
kept apart so the schema's own `.validate()` stays side-effect-free like
every other validation module in this repository, and a rendered-text
banned-phrase scan (`scan_html_for_banned_phrases`) reusing the same
shared registries `workflows.validation`/`phase_space.coordinate`/
`transitions.governance` already reuse -- no new banned-phrase list is
declared here beyond one tiny renderer-specific addition.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Union

from dataset_acquisition.store import ALLOWED_TARGET_ROOT_PREFIXES
from phase_space.coordinate import scan_banned_phrases
from sciencer_d.btc_icft.report_guardrails import BANNED_REPORT_PHRASES
from transitions.governance import TRANSITION_EXTRA_BANNED_PHRASES
from workflows.validation import REPORT_PIPELINE_EXTRA_BANNED_PHRASES

TEMPLATE_VERSION = "workflows.html_renderer v1"

# A small addition specific to rendered HTML output -- catches an
# unescaped/raw external-asset reference slipping into free-text content
# (the renderer itself never emits one; this is a defense-in-depth check
# on the final rendered string, not a claim-language phrase).
HTML_REPORT_PACK_EXTRA_BANNED_PHRASES: tuple[str, ...] = REPORT_PIPELINE_EXTRA_BANNED_PHRASES + (
    "clinically validated report",
)

_ALL_HTML_BANNED_PHRASES: tuple[str, ...] = (
    BANNED_REPORT_PHRASES + TRANSITION_EXTRA_BANNED_PHRASES + HTML_REPORT_PACK_EXTRA_BANNED_PHRASES
)


class HtmlReportPackValidationError(ValueError):
    """Raised when an `HtmlReportPackV1` fails structural validation."""


class HtmlReportPackError(ValueError):
    """Raised for render-level problems (missing source artifact, guardrail
    hit in rendered output, ...) distinct from schema validation."""


def scan_html_for_banned_phrases(html_text: str) -> list[str]:
    """Return every banned phrase (lowercased) found in `html_text` --
    empty list means clean. Never raises; the caller decides whether to
    fail closed (the renderer does; a test can inspect the list)."""
    low = html_text.lower()
    return [phrase for phrase in _ALL_HTML_BANNED_PHRASES if phrase in low]


def _scan_banned_phrases(value: Any, path: str, errors: list[str]) -> None:
    scan_banned_phrases(value, path, errors)
    if isinstance(value, str):
        low = value.lower()
        for phrase in HTML_REPORT_PACK_EXTRA_BANNED_PHRASES:
            if phrase in low:
                errors.append(f"{path}: banned phrase detected: '{phrase}'")
    elif isinstance(value, dict):
        for key, sub in value.items():
            _scan_banned_phrases(sub, f"{path}.{key}", errors)
    elif isinstance(value, (list, tuple)):
        for idx, item in enumerate(value):
            _scan_banned_phrases(item, f"{path}[{idx}]", errors)


def validate_output_root(output_root: Any) -> list[str]:
    """String-level prefix check only (rule 5) -- the real traversal/
    containment safety check is `dataset_acquisition.store.validate_target_root`,
    applied at write time in the renderer."""
    errors: list[str] = []
    if not output_root or not isinstance(output_root, str):
        errors.append("output_root is required (non-empty string) (rule 5)")
        return errors
    raw = output_root.strip()
    if raw.startswith("/") or raw.startswith("~") or ".." in Path(raw).parts:
        errors.append(f"output_root must be a safe relative repository path, got {output_root!r} (rule 5)")
        return errors
    raw_posix = Path(raw).as_posix()
    if not any(raw_posix == prefix.rstrip("/") or raw_posix.startswith(prefix) for prefix in ALLOWED_TARGET_ROOT_PREFIXES):
        errors.append(f"output_root must be under one of {ALLOWED_TARGET_ROOT_PREFIXES}, got {output_root!r} (rule 5)")
    return errors


def validate_html_report_pack(pack: Any) -> list[str]:
    """Return a list of error strings (empty = valid). Never raises; never
    touches the filesystem (see `validate_source_artifacts_exist` for the
    existence check)."""
    errors: list[str] = []

    if not getattr(pack, "report_pack_id", None):
        errors.append("report_pack_id is required")
    if not getattr(pack, "dataset_id", None):
        errors.append("dataset_id is required")

    # Rule 1.
    if not getattr(pack, "limitations", None):
        errors.append("limitations must be a non-empty list (rule 1)")

    # Rule 2.
    if not getattr(pack, "blocked_interpretations", None):
        errors.append("blocked_interpretations must be a non-empty list (rule 2)")

    # Rule 3.
    if not getattr(pack, "source_report_pack_path", None):
        errors.append("source_report_pack_path is required (rule 3)")

    errors.extend(validate_output_root(getattr(pack, "output_root", None)))

    # Rule 10: no claim_scope/evidence_level field of its own.
    if hasattr(pack, "claim_scope") or hasattr(pack, "evidence_level"):
        errors.append(
            "HtmlReportPackV1 must not carry its own claim_scope/evidence_level field -- it may only "
            "present the ceilings already recorded on the referenced ReportPackV1/EvidenceBundleV1 (rule 10)"
        )

    html_pack_id = getattr(pack, "html_pack_id", None)
    if html_pack_id:
        from workflows.html_report_pack import compute_html_pack_id

        expected_id = compute_html_pack_id(
            report_pack_id=getattr(pack, "report_pack_id", None),
            dataset_id=getattr(pack, "dataset_id", None),
            input_mode=getattr(pack, "input_mode", None),
            source_evidence_report_paths=list(getattr(pack, "source_evidence_report_paths", None) or []),
        )
        if html_pack_id != expected_id:
            errors.append(f"html_pack_id '{html_pack_id}' does not match deterministic id '{expected_id}'")

    # Rule 9 / 11: banned-phrase scan over every free-text/structured field.
    for field_name in ("title",):
        _scan_banned_phrases(getattr(pack, field_name, None) or "", field_name, errors)
    for field_name in ("limitations", "blocked_interpretations", "reproducibility_commands", "rendered_sections"):
        _scan_banned_phrases(getattr(pack, field_name, None) or [], field_name, errors)
    _scan_banned_phrases(getattr(pack, "validation_summary", None) or {}, "validation_summary", errors)
    _scan_banned_phrases(getattr(pack, "metadata", None) or {}, "metadata", errors)

    return errors


def validate_source_artifacts_exist(
    *, source_report_pack_path: Union[str, Path], source_evidence_report_paths: list[str],
    source_evidence_bundle_paths: list[str], repo_root: Path,
) -> list[str]:
    """Filesystem-touching existence check (rules 3/4) -- kept separate
    from `validate_html_report_pack` so the schema's own `.validate()`
    stays side-effect-free. An empty `source_evidence_report_paths`/
    `source_evidence_bundle_paths` list is a valid "no report/bundle was
    generated for this run" state, not an error (rule 4) -- only a
    *declared* path that does not resolve on disk is an error."""
    errors: list[str] = []

    report_pack_path = Path(source_report_pack_path)
    if not report_pack_path.is_absolute():
        report_pack_path = repo_root / report_pack_path
    if not report_pack_path.exists():
        errors.append(f"source_report_pack_path does not exist: {source_report_pack_path}")

    for label, paths in (
        ("source_evidence_report_paths", source_evidence_report_paths),
        ("source_evidence_bundle_paths", source_evidence_bundle_paths),
    ):
        for raw in paths or []:
            p = Path(raw)
            if not p.is_absolute():
                p = repo_root / p
            if not p.exists():
                errors.append(f"{label} entry does not exist: {raw}")

    return errors
