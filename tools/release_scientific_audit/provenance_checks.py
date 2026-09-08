"""Audit checks 1, 5, 14: synthetic-vs-empirical provenance, sample-size/
effective-N fields, and missing/incomplete provenance metadata."""
from __future__ import annotations

from typing import List

from .models import Finding, ProvenanceRecord

SYNTHETIC_SOURCE_KINDS: frozenset[str] = frozenset({"synthetic", "synthetic_demo"})
EMPIRICAL_SOURCE_KINDS: frozenset[str] = frozenset({"empirical_local", "empirical_csv", "empirical_labeled"})
REQUIRED_PROVENANCE_FIELDS: tuple[str, ...] = ("source_kind", "dataset_id", "seed")


def check_synthetic_vs_empirical_provenance(records: tuple) -> List[Finding]:
    """Check 1: every provenance record must declare a recognized
    source_kind, and the audit must never treat an unlabeled record as
    empirical by default."""
    findings: List[Finding] = []
    for record in records:
        record: ProvenanceRecord
        if record.source_kind is None:
            findings.append(Finding(
                "synthetic_vs_empirical_provenance", "blocking",
                f"{record.component}: no source_kind declared -- cannot classify as synthetic or empirical",
                f"provenance_records[{record.component}].source_kind",
            ))
        elif record.source_kind not in SYNTHETIC_SOURCE_KINDS | EMPIRICAL_SOURCE_KINDS:
            findings.append(Finding(
                "synthetic_vs_empirical_provenance", "warning",
                f"{record.component}: unrecognized source_kind {record.source_kind!r}",
                f"provenance_records[{record.component}].source_kind",
            ))
        else:
            findings.append(Finding(
                "synthetic_vs_empirical_provenance", "info",
                f"{record.component}: source_kind={record.source_kind!r}",
                f"provenance_records[{record.component}].source_kind",
            ))
    return findings


def check_sample_size_and_effective_n(records: tuple) -> List[Finding]:
    """Check 5: a declared sample_size with no effective_sample_size is a
    real gap -- pseudoreplication/multiplicity corrections need the
    effective (independent-unit) count, not the raw window/row count."""
    findings: List[Finding] = []
    for record in records:
        record: ProvenanceRecord
        if record.sample_size is None:
            findings.append(Finding(
                "sample_size_and_effective_n", "warning",
                f"{record.component}: no sample_size recorded",
                f"provenance_records[{record.component}].sample_size",
            ))
            continue
        if record.effective_sample_size is None:
            findings.append(Finding(
                "sample_size_and_effective_n", "blocking",
                f"{record.component}: sample_size={record.sample_size} recorded but no "
                "effective_sample_size -- cannot distinguish raw rows from independent units",
                f"provenance_records[{record.component}].effective_sample_size",
            ))
        elif record.effective_sample_size > record.sample_size:
            findings.append(Finding(
                "sample_size_and_effective_n", "blocking",
                f"{record.component}: effective_sample_size ({record.effective_sample_size}) exceeds "
                f"sample_size ({record.sample_size}) -- impossible, data is corrupt or mislabeled",
                f"provenance_records[{record.component}]",
            ))
        else:
            findings.append(Finding(
                "sample_size_and_effective_n", "info",
                f"{record.component}: sample_size={record.sample_size}, "
                f"effective_sample_size={record.effective_sample_size}",
                f"provenance_records[{record.component}]",
            ))
    return findings


def check_missing_provenance(records: tuple) -> List[Finding]:
    """Check 14: every required provenance field must be present and
    non-empty; a record with NO provenance data supplied at all is its
    own explicit finding (not silently absent)."""
    findings: List[Finding] = []
    if not records:
        findings.append(Finding(
            "missing_provenance", "blocking",
            "no provenance records were supplied to this audit at all",
            "provenance_records (empty)", insufficient_data=True,
        ))
        return findings
    for record in records:
        record: ProvenanceRecord
        missing = [
            field_name for field_name in REQUIRED_PROVENANCE_FIELDS
            if getattr(record, field_name) in (None, "")
        ]
        if missing:
            findings.append(Finding(
                "missing_provenance", "blocking",
                f"{record.component}: missing required provenance field(s): {', '.join(missing)}",
                f"provenance_records[{record.component}]",
            ))
    return findings
