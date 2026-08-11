"""Filesystem store for one `EvidenceBundleV1` and its sub-artifacts.

Unlike `transitions.store.TransitionStore` and `phase_space.store.PhaseSpaceStore`
(both "one directory per id under a shared root", since an exporter run can
produce many transitions/coordinates into one shared output tree), a bundle
build produces exactly ONE bundle per invocation into ONE explicit `--out`
directory (see `evidence.export_bundle`'s CLI). So this store is scoped to
that single directory rather than a multi-bundle root keyed by bundle_id.

Layout::

    <out>/EvidenceBundle.json
    <out>/transitions/<transition_id>/TransitionRecord.json   (TransitionStore root)
    <out>/phase_space/<transition_id>/PhaseSpaceCoordinates.json  (PhaseSpaceStore root)
    <out>/registry_updated.json   (only when mark_seen was requested)
"""
from __future__ import annotations

from pathlib import Path

from evidence.bundle import EvidenceBundleV1

BUNDLE_FILENAME = "EvidenceBundle.json"
TRANSITIONS_SUBDIR = "transitions"
PHASE_SPACE_SUBDIR = "phase_space"
UPDATED_REGISTRY_FILENAME = "registry_updated.json"


class EvidenceBundleStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    @property
    def transitions_dir(self) -> Path:
        return self.root / TRANSITIONS_SUBDIR

    @property
    def phase_space_dir(self) -> Path:
        return self.root / PHASE_SPACE_SUBDIR

    @property
    def updated_registry_path(self) -> Path:
        return self.root / UPDATED_REGISTRY_FILENAME

    def write(self, bundle: EvidenceBundleV1) -> Path:
        return bundle.write_json(self.root / BUNDLE_FILENAME)

    def read(self) -> EvidenceBundleV1:
        path = self.root / BUNDLE_FILENAME
        if not path.exists():
            raise FileNotFoundError(path)
        return EvidenceBundleV1.from_json(path.read_text(encoding="utf-8"))

    def exists(self) -> bool:
        return (self.root / BUNDLE_FILENAME).exists()
