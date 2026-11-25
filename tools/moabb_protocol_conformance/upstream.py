"""Upstream software references for the MOABB protocol-conformance lane.

No package listed here is imported or executed by this tool. Values were
verified against public primary sources during Batch 2 (2026-10-16).
"""
from __future__ import annotations

from typing import Any, Dict, List

# NeuroTechX/moabb — Mother of All BCI Benchmarks
# LICENSE (BSD-3-Clause): https://github.com/NeuroTechX/moabb/blob/master/LICENSE
# pyproject license text: BSD-3-Clause on develop tip inspected 2026-10-16
# Docs: https://moabb.neurotechx.com/docs/
# Version: dynamic via moabb.__version__; package NOT installed in this lane.
MOABB_REFERENCE: Dict[str, Any] = {
    "name": "moabb",
    "full_name": "Mother of All BCI Benchmarks",
    "repository": "https://github.com/NeuroTechX/moabb",
    "documentation": "https://moabb.neurotechx.com/docs/",
    "license": "BSD-3-Clause",
    "license_source": "https://github.com/NeuroTechX/moabb/blob/master/LICENSE",
    "version_observed": None,  # package not installed; do not invent a pin
    "branch_inspected": "develop",
    "inspection_date": "2026-10-16",
    "integration_mode": "reference_and_pattern_emulation",
    "copied_code": False,
    "executed": False,
    "cloned": False,
    "installed": False,
    "api_surface_referenced": [
        "moabb.datasets.base.BaseDataset (code, paradigm, events/event_id, subjects, sessions_per_subject, doi)",
        "moabb.evaluations WithinSessionEvaluation / CrossSessionEvaluation / CrossSubjectEvaluation / WithinSubjectEvaluation (split semantics, names only)",
    ],
    "notes": (
        "Per-dataset license/access are not exposed as BaseDataset attributes; "
        "this lane therefore preserves unknown unless a fixture/candidate supplies them."
    ),
}

# MNE-Python — interoperability reference only (MOABB depends on mne>=1.13).
# This lane does not import MNE; candidate records may list adapters.mne_bids.
MNE_REFERENCE: Dict[str, Any] = {
    "name": "mne",
    "repository": "https://github.com/mne-tools/mne-python",
    "documentation": "https://mne.tools/stable/index.html",
    "license": "BSD-3-Clause",
    "license_source": "https://github.com/mne-tools/mne-python/blob/main/LICENSE.txt",
    "version_observed": None,
    "integration_mode": "reference_only",
    "copied_code": False,
    "executed": False,
    "cloned": False,
    "installed": False,
    "notes": (
        "MOABB's public pyproject.toml lists mne>=1.13. This conformance tool does not "
        "call MNE; any future signal path remains adapters.mne_bids (out of this lane)."
    ),
}

# In-tree consumer (not external software)
INTREE_REFERENCE: Dict[str, Any] = {
    "name": "dataset_importers.moabb_importer / DatasetCandidateRecordV1",
    "path": "dataset_importers/",
    "integration_mode": "read_only_reuse",
    "copied_code": False,
    "notes": "Offline consumer of candidate metadata; does not modify importer modules.",
}

UPSTREAM_REFERENCES: List[Dict[str, Any]] = [
    MOABB_REFERENCE,
    MNE_REFERENCE,
    INTREE_REFERENCE,
]
