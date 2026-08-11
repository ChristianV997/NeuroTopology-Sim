"""External artifact adapters -- the bridge from lab/user-provided derived
artifacts to this repository's governed schemas.

See docs/mne_bids_adapter.md for the first (and, for this milestone, only)
adapter: `adapters.mne_bids`, which converts explicit MNE/BIDS-style
metadata and derived feature tables into `DatasetRecordV1`/
`ArtifactRecordV1`/`TransitionRecordV1` (and, optionally,
`PhaseSpaceCoordinateV1`/`EvidenceBundleV1`/`EvidenceReportV1`) artifacts.
It does not run raw EEG/MEG/iEEG/fNIRS preprocessing, does not download
datasets, and does not infer state labels from column names or file paths.

`adapters.mne_bids` is deliberately NOT re-exported here: it is also the
CLI entry point (`python -m adapters.mne_bids`), and eagerly importing it
from this package's __init__ causes Python to double-import it under `-m`,
the same problem `phase_space/__init__.py`, `benchmarks/__init__.py`,
`evidence/__init__.py`, `reports/__init__.py`, and `external_tools/__init__.py`
already avoid for their own CLI modules. Import what you need directly,
e.g. `from adapters.mne_bids import scan_bids_metadata,
export_mne_bids_derived_transitions`.
"""
from __future__ import annotations

__all__: list[str] = []
