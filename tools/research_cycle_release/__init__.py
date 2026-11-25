"""Read-only research-cycle release-evidence evaluator."""
from __future__ import annotations

from tools.research_cycle_release.schema import (
    BUNDLE_SCHEMA,
    SCHEMA_VERSION,
    DecisionState,
    ReleaseEvidenceReport,
)

__all__ = [
    "BUNDLE_SCHEMA",
    "SCHEMA_VERSION",
    "DecisionState",
    "ReleaseEvidenceReport",
    "evaluate_research_cycle_release",
    "dumps",
    "render_markdown",
    "write_reports",
]


def __getattr__(name: str):
    if name == "evaluate_research_cycle_release":
        from tools.research_cycle_release.evaluator import evaluate_research_cycle_release

        return evaluate_research_cycle_release
    if name in {"dumps", "render_markdown", "write_reports"}:
        from tools.research_cycle_release import report as report_mod

        return getattr(report_mod, name)
    raise AttributeError(name)
