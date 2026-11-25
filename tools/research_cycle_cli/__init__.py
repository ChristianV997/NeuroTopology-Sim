"""Read-only inspection CLI for Awareness Studio research-cycle state.

Answers operator questions about research-cycle ledger state, claims,
hypotheses, artifacts, and evidence graphs by reading -- never writing,
never executing, never discovering -- the outputs of other, independently
owned tools:

- the research-cycle ledger (a SQLite database; schema mirrored from
  ``apps/awareness_studio/src/awareness_studio/research_cycle/{models,ledger}.py``,
  Batch 1 / codex, read-only, not imported),
- the scientific claim gate's report output (schema mirrored from
  ``tools/research_claim_gate/gate.py``, Batch 1 / codex, read-only),
- the simulation-artifact extractor's report output (schema mirrored from
  ``tools/simulation_artifacts/extractor.py``, Batch 1 / codex, read-only).

This package is self-contained (stdlib only) and never imports any of the
three packages above -- if a Batch 1 module isn't available in a given
checkout, this CLI still works against any file that matches its
documented shape (see docs/awareness_studio/research_cycle_cli.md).
"""
from __future__ import annotations

from tools.research_cycle_cli.versions import COMPILER_VERSION, REPORT_SCHEMA_VERSION

__all__ = ["COMPILER_VERSION", "REPORT_SCHEMA_VERSION"]
