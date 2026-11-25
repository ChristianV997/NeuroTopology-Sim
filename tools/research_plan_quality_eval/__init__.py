"""Offline evaluation harness for the research-plan quality rubric.

This package tests how the existing 20-dimension rubric in
``tools.research_plan_quality`` behaves on versioned synthetic fixtures. It
adds fixture manifests with hashes, group-level splits, cross-split duplicate
detection, a separate label file, and development/held-out access guards.

It does not define a second rubric, change any rubric dimension, or measure
criterion leakage, human agreement, or generalisation. It makes no network
calls and no model calls. A rubric score is not scientific confirmation.
"""
from .harness import DEFAULT_MANIFEST, build_report, label_consistency, to_report_json

__all__ = ["DEFAULT_MANIFEST", "build_report", "label_consistency", "to_report_json"]
