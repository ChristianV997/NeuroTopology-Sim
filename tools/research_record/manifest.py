"""Input manifest resolution for the research-record compiler.

The compiler never discovers input files on its own (no directory
scanning, no network, no ``git``/``gh`` calls -- rule 13). A manifest file
(JSON or YAML) names, per input contract, the path to the evidence
document that satisfies it. Any key the manifest omits is treated as an
explicitly missing input, never as a signal to infer a value some other
way (rule 9).
"""
from __future__ import annotations

from pathlib import Path

from tools.research_record.evidence_loader import LoadResult, load_evidence_file

RECONCILIATION = "reconciliation"                # PR matrix
AGENT_CONTRIBUTIONS = "agent_contributions"
DASHBOARD_ISOLATION = "dashboard_isolation"
TEST_RUNNER = "test_runner"                       # test summaries + CI classification
PERFORMANCE_BENCHMARK = "performance_benchmark"
MEMORY_EVIDENCE = "memory_evidence"
DATASET_PROVENANCE = "dataset_provenance"          # provenance reports
COHORT_READINESS = "cohort_readiness"              # empirical-readiness reports
TOPOLOGY_VALIDATION = "topology_validation"        # topology summaries
FALSIFICATION = "falsification"
MERGE_GATE = "merge_gate"
RELEASE_MANIFEST = "release_manifest"
SCIENTIFIC_GATE_REPORTS = "scientific_gate_reports"
BLOCKER_REPORTS = "blocker_reports"                # externally-reported blockers
ARTIFACT_REFERENCES = "artifact_references"        # artifact paths (references only, never read)
OPERATOR_NOTES = "operator_notes"

# Canonical input-section keys and the top-level list key each one's JSON/
# YAML/CSV body is expected to carry (None for a section whose contract is
# a single flat object rather than a list of rows).
SECTION_LIST_KEYS: dict[str, str | None] = {
    RECONCILIATION: "pull_requests",
    AGENT_CONTRIBUTIONS: "contributions",
    DASHBOARD_ISOLATION: None,
    TEST_RUNNER: "jobs",
    PERFORMANCE_BENCHMARK: "benchmarks",
    MEMORY_EVIDENCE: "benchmarks",
    DATASET_PROVENANCE: "datasets",
    COHORT_READINESS: "cohorts",
    TOPOLOGY_VALIDATION: "checks",
    FALSIFICATION: "results",
    MERGE_GATE: "decisions",
    RELEASE_MANIFEST: None,
    SCIENTIFIC_GATE_REPORTS: "gates",
    BLOCKER_REPORTS: "blockers",
    ARTIFACT_REFERENCES: "artifacts",
    OPERATOR_NOTES: "notes",
}

INPUT_SECTIONS: tuple[str, ...] = tuple(SECTION_LIST_KEYS)

_NOT_PROVIDED = "not_provided"


def load_manifest(manifest_path: Path) -> dict[str, LoadResult]:
    """Resolve every input section named in ``manifest_path``.

    Returns a dict keyed by section name -> ``LoadResult``. Sections absent
    from the manifest get a ``LoadResult`` with ``error="not_provided"``.
    Relative paths inside the manifest are resolved against the manifest's
    own parent directory so fixtures/manifests remain relocatable. The
    manifest file itself may be JSON or YAML.
    """
    manifest_result = load_evidence_file(manifest_path)
    if not manifest_result.ok:
        return {
            section: LoadResult(
                path=None,
                ok=False,
                data=None,
                error=f"manifest_load_failed: {manifest_result.error}",
                sha256=None,
                format=None,
            )
            for section in INPUT_SECTIONS
        }

    manifest_data = manifest_result.data if isinstance(manifest_result.data, dict) else {}
    base_dir = manifest_path.resolve().parent

    resolved: dict[str, LoadResult] = {}
    for section in INPUT_SECTIONS:
        raw_value = manifest_data.get(section)
        if not isinstance(raw_value, str) or not raw_value.strip():
            resolved[section] = LoadResult(path=None, ok=False, data=None, error=_NOT_PROVIDED, sha256=None, format=None)
            continue

        candidate = Path(raw_value)
        section_path = candidate if candidate.is_absolute() else (base_dir / candidate)
        resolved[section] = load_evidence_file(section_path, list_key=SECTION_LIST_KEYS[section])

    return resolved
