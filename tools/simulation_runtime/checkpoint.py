"""Atomic checkpointing and resumption state management for simulation campaigns.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from tools.simulation_runtime.atomic_io import (
    compute_sha256,
    load_json,
    write_atomic_json,
)
from tools.simulation_runtime.types import (
    CampaignManifest,
    CampaignState,
    Outcome,
    UnitResult,
    WorkUnit,
)


class CheckpointError(Exception):
    """Base exception for campaign checkpoint errors."""


class CheckpointMismatchError(CheckpointError):
    """Raised when resuming against a mismatched campaign or configuration hash."""


class CheckpointCorruptError(CheckpointError):
    """Raised when a checkpoint file or per-unit result file is corrupted."""


class CampaignCheckpointManager:
    """Manages atomic checkpoints and per-unit persistence for a simulation campaign.

    Directory layout:
        <output_dir>/
            manifest.json           # Copy of input campaign manifest
            checkpoint.json         # Latest aggregated campaign state (updated after every unit)
            units/
                <unit_id>.json      # Atomic per-unit result
    """

    def __init__(self, output_dir: Path | str, manifest: CampaignManifest) -> None:
        self.output_dir = Path(output_dir).resolve()
        self.manifest = manifest
        self.units_dir = self.output_dir / "units"
        self.checkpoint_path = self.output_dir / "checkpoint.json"
        self.manifest_path = self.output_dir / "manifest.json"

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.units_dir.mkdir(parents=True, exist_ok=True)

    def initialize_or_resume(self, *, resume: bool = False) -> Tuple[CampaignState, Set[str]]:
        """Initialize new campaign state or resume from existing checkpoint.

        Returns:
            (campaign_state, completed_unit_ids)
        """
        # Always write / verify manifest copy
        if not self.manifest_path.exists():
            write_atomic_json(self.manifest_path, self.manifest.to_dict())

        if not resume:
            # Fresh run: verify no active or conflicting checkpoint, or wipe if clean requested
            state = self._build_initial_state()
            self._save_checkpoint(state)
            return state, set()

        # Resuming: load checkpoint if available
        if not self.checkpoint_path.exists():
            # Nothing to resume yet; start fresh state
            state = self._build_initial_state()
            self._save_checkpoint(state)
            return state, set()

        try:
            raw_state = load_json(self.checkpoint_path)
            state = CampaignState.from_dict(raw_state)
        except Exception as exc:
            raise CheckpointCorruptError(f"Failed to read checkpoint at {self.checkpoint_path}: {exc}") from exc

        # Verify campaign_id and configuration hash
        if state.campaign_id != self.manifest.campaign_id:
            raise CheckpointMismatchError(
                f"Checkpoint campaign_id ({state.campaign_id}) does not match manifest "
                f"({self.manifest.campaign_id})"
            )
        if state.manifest_hash != self.manifest.configuration_hash:
            raise CheckpointMismatchError(
                f"Checkpoint configuration hash ({state.manifest_hash}) does not match manifest "
                f"({self.manifest.configuration_hash})"
            )

        # Re-verify and reconcile per-unit files
        completed_ids: Set[str] = set()
        for unit in self.manifest.units:
            unit_file = self.units_dir / f"{unit.unit_id}.json"
            if unit_file.exists():
                try:
                    unit_data = load_json(unit_file)
                    result = UnitResult.from_dict(unit_data)
                    state.completed_units[unit.unit_id] = result
                    # Only mark as completed if it has a terminal outcome
                    if result.outcome != Outcome.NOT_RUN:
                        completed_ids.add(unit.unit_id)
                except Exception as exc:
                    raise CheckpointCorruptError(
                        f"Corrupt unit result file {unit_file}: {exc}"
                    ) from exc

        # When resuming, un-cancel the campaign state so remaining units can complete
        state.cancelled = False
        self._update_summary_and_status(state)
        self._save_checkpoint(state)
        return state, completed_ids

    def record_unit_completed(
        self,
        state: CampaignState,
        result: UnitResult,
    ) -> None:
        """Atomically record unit completion and update campaign checkpoint."""
        unit_file = self.units_dir / f"{result.unit_id}.json"
        write_atomic_json(unit_file, result.to_dict())

        state.completed_units[result.unit_id] = result
        state.active_unit = None
        self._update_summary_and_status(state)
        self._save_checkpoint(state)

    def mark_cancelled(self, state: CampaignState) -> None:
        """Mark campaign state as cancelled."""
        state.cancelled = True
        state.active_unit = None
        self._update_summary_and_status(state)
        self._save_checkpoint(state)

    def _build_initial_state(self) -> CampaignState:
        summary = {outcome.value: 0 for outcome in Outcome}
        summary[Outcome.NOT_RUN.value] = len(self.manifest.units)
        return CampaignState(
            schema_version="simulation_campaign_state_v1",
            campaign_id=self.manifest.campaign_id,
            manifest_hash=self.manifest.configuration_hash,
            completed_units={},
            active_unit=None,
            is_complete=False,
            is_partial=True,
            cancelled=False,
            summary=summary,
            last_checkpoint_at=datetime.now(timezone.utc).isoformat(),
        )

    def _update_summary_and_status(self, state: CampaignState) -> None:
        summary = {outcome.value: 0 for outcome in Outcome}
        total_units = len(self.manifest.units)

        for unit in self.manifest.units:
            if unit.unit_id in state.completed_units:
                res = state.completed_units[unit.unit_id]
                summary[res.outcome.value] += 1
            else:
                summary[Outcome.NOT_RUN.value] += 1

        state.summary = summary
        all_terminal = sum(summary[o.value] for o in Outcome if o != Outcome.NOT_RUN) == total_units
        state.is_complete = all_terminal and not state.cancelled
        state.is_partial = not state.is_complete
        state.last_checkpoint_at = datetime.now(timezone.utc).isoformat()

    def _save_checkpoint(self, state: CampaignState) -> None:
        write_atomic_json(self.checkpoint_path, state.to_dict())
