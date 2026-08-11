"""Metadata-first dataset candidate importers (MOABB, EEGDash, ...).

See docs/dataset_candidate_importers.md. This package never downloads raw
datasets and never treats a candidate record as evidence -- it produces
`DatasetCandidateRecordV1` scouting records only. Deliberately mirrors
`adapters/__init__.py`: kept empty so `python -m
dataset_importers.export_candidates` does not get imported twice via both
`dataset_importers` and `dataset_importers.export_candidates` on the
module search path.
"""
from __future__ import annotations

__all__: list[str] = []
