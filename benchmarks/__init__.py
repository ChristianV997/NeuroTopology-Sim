"""Benchmark dataset/artifact registry and split/holdout governance.

See docs/benchmark_dataset_registry.md for the full rationale. This
package tracks HOW each dataset and committed artifact may be used across
the research pipeline (exploration, development, locked internal/external
validation, prospective testing, retired, deprecated) -- not scientific
results. It is deliberately narrow: a record shape (`DatasetRecordV1`,
`ArtifactRecordV1`), a use-policy (`benchmarks.split_policy`), a validation
holdout lock (`benchmarks.holdout_lock`), structural validation
(`benchmarks.validation`), and a registry store + CLI
(`benchmarks.export_registry`). It does not implement Theory Competition,
Koopman/DMD, Counterfactual Reachable Sets, a Phenomenology parser, the
Holo-Atlas interpreter, or a Consciousness Atlas -- it exists so that those,
if built later, cannot accidentally treat an already-seen exploratory
dataset as independent confirmatory evidence.
"""
from __future__ import annotations

from benchmarks.artifact_registry import ArtifactRecordV1
from benchmarks.dataset_registry import DatasetRecordV1

# BenchmarkRegistry (benchmarks.export_registry) is deliberately NOT
# re-exported here: that module is also the CLI entry point
# (`python -m benchmarks.export_registry`), and eagerly importing it from
# this package's __init__ causes Python to double-import it (once as
# `benchmarks.export_registry`, once as `__main__`) under `-m`, exactly the
# problem `phase_space/__init__.py` avoids for
# `phase_space.export_from_transitions`. Import it directly:
# `from benchmarks.export_registry import BenchmarkRegistry`.

__all__ = ["DatasetRecordV1", "ArtifactRecordV1"]
