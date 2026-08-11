"""Safe, disk-bounded, dry-run-first acquisition planning for selected
`dataset_importers.DatasetCandidateRecordV1` candidates.

See docs/dataset_acquisition_planner.md. This package never downloads raw
data by default and never treats a plan/manifest as evidence. Deliberately
mirrors `adapters/__init__.py`/`dataset_importers/__init__.py`: kept empty
so `python -m dataset_acquisition.export_plan` is not imported twice via
both `dataset_acquisition` and `dataset_acquisition.export_plan`.
"""
from __future__ import annotations

__all__: list[str] = []
