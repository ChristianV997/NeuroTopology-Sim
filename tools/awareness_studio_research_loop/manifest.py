"""Input manifest resolution for the Awareness Studio research-cycle
orchestrator.

The orchestrator never discovers input files, scripts, or evidence on its
own -- no directory scanning, no network, no ``git``/``gh`` calls, and it
never executes anything it reads. A manifest file (JSON or YAML) names,
per input contract, the path to the evidence document that satisfies it.
A key the manifest omits is treated as an explicitly missing input, never
inferred another way.
"""
from __future__ import annotations

from pathlib import Path

from tools.awareness_studio_research_loop.evidence_loader import LoadResult, load_evidence_file

#: Owned by Claude A (tools/awareness_studio_research/**, not modified or
#: imported here). Consumed as a flat export document with the exact
#: record shapes that package's models.py produces: sources, claims,
#: correlates, hypothesis_links, dataset_links, experiment_links,
#: evidence_updates.
LITERATURE_EVIDENCE = "literature_evidence"
#: Owned by Antigravity C (not modified or imported here).
HYPOTHESIS_REGISTRY = "hypothesis_registry"
EXPERIMENT_PLANS = "experiment_plans"
EXECUTION_RESULTS = "execution_results"
NULL_SURROGATE_RESULTS = "null_surrogate_results"
VALIDATION_REPORTS = "validation_reports"
REVIEWER_DECISIONS = "reviewer_decisions"
THEORY_STATE = "theory_state"
CYCLE_CONFIG = "cycle_config"

# Canonical input-section keys and the top-level list key each one's JSON/
# YAML/CSV body is expected to carry (None for a section whose contract is
# a single flat object, or an object with several named lists, rather
# than one list of rows).
SECTION_LIST_KEYS: dict[str, str | None] = {
    LITERATURE_EVIDENCE: None,
    HYPOTHESIS_REGISTRY: "hypotheses",
    EXPERIMENT_PLANS: "plans",
    EXECUTION_RESULTS: "executions",
    NULL_SURROGATE_RESULTS: "null_tests",
    VALIDATION_REPORTS: "reports",
    REVIEWER_DECISIONS: "decisions",
    THEORY_STATE: None,
    CYCLE_CONFIG: None,
}

INPUT_SECTIONS: tuple[str, ...] = tuple(SECTION_LIST_KEYS)

_NOT_PROVIDED = "not_provided"


def load_manifest(manifest_path: Path) -> dict[str, LoadResult]:
    """Resolve every input section named in ``manifest_path``.

    Returns a dict keyed by section name -> ``LoadResult``. Sections absent
    from the manifest get a ``LoadResult`` with ``error="not_provided"``.
    Relative paths inside the manifest resolve against the manifest's own
    parent directory. The manifest file itself may be JSON or YAML.
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
