"""Input manifest resolution for the research-state report compiler.

The compiler never discovers input files on its own (no directory scanning,
no ``git`` calls). A manifest JSON file names, per input contract, the path
to the evidence document that satisfies it. Any key the manifest omits is
treated as an explicitly-missing input (see ``docs/research/report_contract.md``),
never as a signal to infer a value some other way.
"""
from __future__ import annotations

from pathlib import Path

from tools.research_report.json_safe import LoadResult, load_json_strict

# Canonical input-section keys. Order here is the canonical iteration order
# used throughout the compiler and in rendered output.
RECONCILIATION = "reconciliation"
CAPABILITY_SNAPSHOT = "capability_snapshot"
DATASET_PROVENANCE = "dataset_provenance"
FALSIFICATION = "falsification"
PERFORMANCE_BENCHMARK = "performance_benchmark"
MEMORY_EVIDENCE = "memory_evidence"
INTEROPERABILITY = "interoperability"
TOPOLOGY_VALIDATION = "topology_validation"
TEST_RUNNER = "test_runner"
MERGE_GATE = "merge_gate"
PR_RETIREMENT = "pr_retirement"

INPUT_SECTIONS: tuple[str, ...] = (
    RECONCILIATION,
    CAPABILITY_SNAPSHOT,
    DATASET_PROVENANCE,
    FALSIFICATION,
    PERFORMANCE_BENCHMARK,
    MEMORY_EVIDENCE,
    INTEROPERABILITY,
    TOPOLOGY_VALIDATION,
    TEST_RUNNER,
    MERGE_GATE,
    PR_RETIREMENT,
)

_NOT_PROVIDED = "not_provided"


def load_manifest(manifest_path: Path) -> dict[str, LoadResult]:
    """Resolve every input section named in ``manifest_path``.

    Returns a dict keyed by section name -> ``LoadResult``. Sections absent
    from the manifest get a ``LoadResult`` with ``error="not_provided"``.
    Relative paths inside the manifest are resolved against the manifest's
    own parent directory so fixtures/manifests remain relocatable.
    """
    manifest_result = load_json_strict(manifest_path)
    if not manifest_result.ok:
        return {
            section: LoadResult(
                path=None,
                ok=False,
                data=None,
                error=f"manifest_load_failed: {manifest_result.error}",
                sha256=None,
            )
            for section in INPUT_SECTIONS
        }

    manifest_data = manifest_result.data if isinstance(manifest_result.data, dict) else {}
    base_dir = manifest_path.resolve().parent

    resolved: dict[str, LoadResult] = {}
    for section in INPUT_SECTIONS:
        raw_value = manifest_data.get(section)
        if not isinstance(raw_value, str) or not raw_value.strip():
            resolved[section] = LoadResult(path=None, ok=False, data=None, error=_NOT_PROVIDED, sha256=None)
            continue

        candidate = Path(raw_value)
        section_path = candidate if candidate.is_absolute() else (base_dir / candidate)
        resolved[section] = load_json_strict(section_path)

    return resolved
