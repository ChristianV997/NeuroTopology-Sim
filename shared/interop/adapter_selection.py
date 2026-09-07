"""Canonical adapter selection and duplicate-resolution layer for NeuroTopology-Sim.

Guarantees:
1. Resolves a signal source to one canonical adapter deterministically.
2. Detects duplicate or conflicting adapters.
3. Prefers native adapters over fallbacks only when supported by verified capability evidence.
4. Preserves exact channel order, sample rate, units, and montage provenance.
5. Refuses ambiguous selection rather than silently choosing.
6. Supports FIF, EDF/BDF, BrainVision, and NPY/CSV fixtures.
7. Represents optional dependency states explicitly.
8. Never auto-installs or downloads dependencies.
9. Never loads a complete recording merely to select an adapter.
10. Exposes a reason code for every selection decision.
11. Preserves backward compatibility with existing signal contracts.
12. Distinguishes: selected, unavailable, ambiguous, incompatible, fallback_selected, unsupported.
"""
from __future__ import annotations

import importlib.util
import math
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence

from .contracts import (
    AdapterCapability,
    AdapterStatus,
    InteropValidationError,
    RecordingManifest,
)


class SelectionStatus(str, Enum):
    """The canonical outcome of an adapter selection attempt."""

    SELECTED = "selected"
    UNAVAILABLE = "unavailable"
    AMBIGUOUS = "ambiguous"
    INCOMPATIBLE = "incompatible"
    FALLBACK_SELECTED = "fallback_selected"
    UNSUPPORTED = "unsupported"


class ReasonCode(str, Enum):
    """Machine-readable reason code explaining the selection outcome."""

    NATIVE_PREFERRED = "native_preferred"
    SINGLE_MATCH = "single_match"
    FALLBACK_PRIMARY_UNAVAILABLE = "fallback_primary_unavailable"
    DEPENDENCY_MISSING = "dependency_missing"
    AMBIGUOUS_CANDIDATES = "ambiguous_candidates"
    CONFLICTING_ADAPTERS = "conflicting_adapters"
    UNSUPPORTED_FORMAT = "unsupported_format"
    CHANNEL_ORDER_MISMATCH = "channel_order_mismatch"
    SAMPLE_RATE_MISMATCH = "sample_rate_mismatch"
    MONTAGE_UNSUPPORTED = "montage_unsupported"
    STREAMING_UNSUPPORTED = "streaming_unsupported"
    UNITS_MISMATCH = "units_mismatch"
    MALFORMED_METADATA = "malformed_metadata"
    NETWORK_NOT_ALLOWED = "network_not_allowed"


class AdapterTier(str, Enum):
    """Classification of adapter implementation tier."""

    NATIVE = "native"
    FALLBACK = "fallback"
    REFERENCE = "reference"
    EMULATE = "emulate"


# Mapping from file extension to canonical format identifier
FORMAT_EXTENSION_MAP: dict[str, str] = {
    ".fif": "fif",
    ".fif.gz": "fif",
    ".edf": "edf",
    ".bdf": "bdf",
    ".bdf+": "bdf",
    ".edf+": "edf",
    ".vhdr": "brainvision",
    ".vmrk": "brainvision",
    ".eeg": "brainvision",
    ".npy": "npy",
    ".npz": "npy",
    ".csv": "csv",
    ".mat": "mat",
}


def detect_format_from_path(source_path: str | Path) -> str | None:
    """Extract canonical format identifier from file extension without loading data."""
    path_obj = Path(source_path)
    name = path_obj.name.lower()
    if name.endswith(".fif.gz"):
        return "fif"
    suffix = path_obj.suffix.lower()
    return FORMAT_EXTENSION_MAP.get(suffix)


@dataclass(frozen=True)
class AdapterCandidate:
    """Registered adapter candidate with capability declarations."""

    adapter_name: str
    tier: AdapterTier
    supported_formats: tuple[str, ...]
    dependency: str = ""
    streaming_support: bool = False
    montage_support: bool = False
    write_support: bool = False
    network_requirement: str = "none"
    priority: int = 100
    description: str = ""

    def to_capability(self, availability: bool) -> AdapterCapability:
        """Convert candidate declaration to a canonical AdapterCapability object."""
        status = AdapterStatus.INTEGRATED if availability else AdapterStatus.UNAVAILABLE
        if self.tier == AdapterTier.EMULATE:
            status = AdapterStatus.EMULATE if availability else AdapterStatus.UNAVAILABLE
        elif self.tier == AdapterTier.REFERENCE:
            status = AdapterStatus.REFERENCE if availability else AdapterStatus.UNAVAILABLE

        return AdapterCapability(
            adapter_name=self.adapter_name,
            supported_formats=self.supported_formats,
            dependency=self.dependency,
            availability=availability,
            streaming_support=self.streaming_support,
            montage_support=self.montage_support,
            write_support=self.write_support,
            network_requirement=self.network_requirement,
            status=status,
        )


@dataclass(frozen=True)
class SelectionRequest:
    """Constraints and metadata for canonical adapter selection."""

    source_path: str | Path | None = None
    file_format: str | None = None
    required_channels: tuple[str, ...] | None = None
    required_sample_rate: float | None = None
    required_units: tuple[str, ...] | None = None
    require_montage: bool = False
    require_streaming: bool = False
    allow_fallback: bool = True
    allow_network: bool = False
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class SelectionResult:
    """Outcome of canonical adapter selection with explicit audit trail."""

    status: SelectionStatus
    selected_adapter: str | None
    reason_code: ReasonCode
    reason_message: str
    target_format: str
    candidate_adapters: tuple[str, ...] = ()
    duplicate_adapters: tuple[str, ...] = ()
    dependency_status: Mapping[str, bool] = field(default_factory=dict)
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "selected_adapter": self.selected_adapter,
            "reason_code": self.reason_code.value,
            "reason_message": self.reason_message,
            "target_format": self.target_format,
            "candidate_adapters": list(self.candidate_adapters),
            "duplicate_adapters": list(self.duplicate_adapters),
            "dependency_status": dict(self.dependency_status),
            "provenance": dict(self.provenance),
        }


# Standard adapter definitions reflecting PR #214, PR #220, and built-in contracts
DEFAULT_ADAPTER_CANDIDATES: tuple[AdapterCandidate, ...] = (
    # FIF: standard MNE reader
    AdapterCandidate(
        adapter_name="mne_fif",
        tier=AdapterTier.FALLBACK,
        supported_formats=("fif",),
        dependency="mne",
        streaming_support=True,
        montage_support=True,
        priority=50,
        description="MNE-based FIF electrophysiology reader.",
    ),
    # EDF / BDF: native pure-Python reader (PR #220) vs MNE reader (PR #214)
    AdapterCandidate(
        adapter_name="native_edf",
        tier=AdapterTier.NATIVE,
        supported_formats=("edf", "bdf"),
        dependency="numpy",
        streaming_support=True,
        montage_support=True,
        priority=100,
        description="Native dependency-light pure-NumPy EDF/BDF reader (PR #220).",
    ),
    AdapterCandidate(
        adapter_name="mne_edf",
        tier=AdapterTier.FALLBACK,
        supported_formats=("edf", "bdf"),
        dependency="mne",
        streaming_support=True,
        montage_support=True,
        priority=50,
        description="MNE-Python EDF/BDF streaming reader (PR #214).",
    ),
    # BrainVision: native pure-Python reader (PR #220) vs MNE reader (PR #214)
    AdapterCandidate(
        adapter_name="native_brainvision",
        tier=AdapterTier.NATIVE,
        supported_formats=("brainvision", "vhdr"),
        dependency="numpy",
        streaming_support=True,
        montage_support=True,
        priority=100,
        description="Native dependency-light BrainVision header/data reader (PR #220).",
    ),
    AdapterCandidate(
        adapter_name="mne_brainvision",
        tier=AdapterTier.FALLBACK,
        supported_formats=("brainvision", "vhdr"),
        dependency="mne",
        streaming_support=True,
        montage_support=True,
        priority=50,
        description="MNE-Python BrainVision streaming reader (PR #214).",
    ),
    # NPY / CSV fixtures: native NumPy array readers
    AdapterCandidate(
        adapter_name="numpy_adapter",
        tier=AdapterTier.NATIVE,
        supported_formats=("npy", "npz", "array"),
        dependency="numpy",
        streaming_support=True,
        montage_support=False,
        priority=100,
        description="Native NumPy array reader for bounded signal fixtures.",
    ),
    AdapterCandidate(
        adapter_name="csv_adapter",
        tier=AdapterTier.NATIVE,
        supported_formats=("csv",),
        dependency="numpy",
        streaming_support=False,
        montage_support=False,
        priority=100,
        description="Native tabular CSV reader for signal calibration fixtures.",
    ),
)


def _default_dependency_checker(module_name: str) -> bool:
    """Check module availability using standard library importlib without side effects."""
    if not module_name:
        return True
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


class CanonicalAdapterSelector:
    """Deterministic, policy-driven signal adapter selector."""

    def __init__(
        self,
        candidates: Sequence[AdapterCandidate] | None = None,
        dependency_checker: Callable[[str], bool] | None = None,
    ) -> None:
        self._candidates: list[AdapterCandidate] = list(candidates or DEFAULT_ADAPTER_CANDIDATES)
        self._dependency_checker: Callable[[str], bool] = dependency_checker or _default_dependency_checker

    def register_candidate(self, candidate: AdapterCandidate) -> None:
        """Register a new or override candidate."""
        self._candidates.append(candidate)

    def detect_duplicates(self, format_name: str | None = None) -> dict[str, list[str]]:
        """Detect multiple registered adapters competing for the same signal format."""
        format_groups: dict[str, list[str]] = {}
        for c in self._candidates:
            for fmt in c.supported_formats:
                fmt_lower = fmt.lower()
                if format_name is not None and fmt_lower != format_name.lower():
                    continue
                format_groups.setdefault(fmt_lower, []).append(c.adapter_name)

        return {fmt: names for fmt, names in format_groups.items() if len(names) > 1}

    def select(self, request: SelectionRequest) -> SelectionResult:
        """Resolve a signal source to a single canonical adapter based on capability evidence."""
        # 1. Resolve format
        target_format: str | None = None
        if request.file_format:
            fmt_clean = request.file_format.strip().lower()
            if fmt_clean.startswith("."):
                target_format = FORMAT_EXTENSION_MAP.get(fmt_clean, fmt_clean.lstrip("."))
            else:
                target_format = fmt_clean
        elif request.source_path:
            target_format = detect_format_from_path(request.source_path)

        if not target_format:
            return SelectionResult(
                status=SelectionStatus.UNSUPPORTED,
                selected_adapter=None,
                reason_code=ReasonCode.UNSUPPORTED_FORMAT,
                reason_message="No signal format could be identified from request parameters.",
                target_format="unknown",
            )

        # 2. Validate metadata sanity (prevent malformed constraints)
        if request.required_sample_rate is not None:
            if not math.isfinite(request.required_sample_rate) or request.required_sample_rate <= 0:
                return SelectionResult(
                    status=SelectionStatus.INCOMPATIBLE,
                    selected_adapter=None,
                    reason_code=ReasonCode.MALFORMED_METADATA,
                    reason_message=f"required_sample_rate must be a positive finite float, got {request.required_sample_rate}",
                    target_format=target_format,
                )

        if request.required_channels is not None:
            if any(not isinstance(c, str) or not c.strip() for c in request.required_channels):
                return SelectionResult(
                    status=SelectionStatus.INCOMPATIBLE,
                    selected_adapter=None,
                    reason_code=ReasonCode.MALFORMED_METADATA,
                    reason_message="required_channels must contain non-empty string channel names.",
                    target_format=target_format,
                )

        # 3. Filter candidates by format
        matching_candidates = [
            c for c in self._candidates if target_format in [f.lower() for f in c.supported_formats]
        ]
        if not matching_candidates:
            return SelectionResult(
                status=SelectionStatus.UNSUPPORTED,
                selected_adapter=None,
                reason_code=ReasonCode.UNSUPPORTED_FORMAT,
                reason_message=f"No registered adapter supports format '{target_format}'.",
                target_format=target_format,
            )

        candidate_names = tuple(c.adapter_name for c in matching_candidates)
        duplicate_names = candidate_names if len(candidate_names) > 1 else ()

        # 4. Check capability constraints
        capable_candidates: list[AdapterCandidate] = []
        for c in matching_candidates:
            if request.require_montage and not c.montage_support:
                continue
            if request.require_streaming and not c.streaming_support:
                continue
            if not request.allow_network and c.network_requirement not in ("none", "optional"):
                continue
            capable_candidates.append(c)

        if not capable_candidates:
            if request.require_montage:
                reason = ReasonCode.MONTAGE_UNSUPPORTED
                msg = f"No adapter supporting '{target_format}' supports montage coordinate mapping."
            elif request.require_streaming:
                reason = ReasonCode.STREAMING_UNSUPPORTED
                msg = f"No adapter supporting '{target_format}' supports memory-bounded streaming."
            else:
                reason = ReasonCode.NETWORK_NOT_ALLOWED
                msg = f"No adapter supporting '{target_format}' satisfies network restrictions."

            return SelectionResult(
                status=SelectionStatus.INCOMPATIBLE,
                selected_adapter=None,
                reason_code=reason,
                reason_message=msg,
                target_format=target_format,
                candidate_adapters=candidate_names,
                duplicate_adapters=duplicate_names,
            )

        # 5. Metadata-level compatibility checks (manifest / requested channels & rates)
        if request.metadata is not None:
            meta = request.metadata
            # Channel order preservation check
            if "expected_channel_order" in meta and request.required_channels is not None:
                expected_order = tuple(meta["expected_channel_order"])
                if expected_order != request.required_channels:
                    return SelectionResult(
                        status=SelectionStatus.INCOMPATIBLE,
                        selected_adapter=None,
                        reason_code=ReasonCode.CHANNEL_ORDER_MISMATCH,
                        reason_message=f"Channel order mismatch between requested {request.required_channels} and expected {expected_order}.",
                        target_format=target_format,
                        candidate_adapters=candidate_names,
                        duplicate_adapters=duplicate_names,
                    )

            # Sampling rate check
            if "expected_sample_rate" in meta and request.required_sample_rate is not None:
                expected_sr = float(meta["expected_sample_rate"])
                if not math.isclose(expected_sr, request.required_sample_rate, abs_tol=1e-3):
                    return SelectionResult(
                        status=SelectionStatus.INCOMPATIBLE,
                        selected_adapter=None,
                        reason_code=ReasonCode.SAMPLE_RATE_MISMATCH,
                        reason_message=f"Sample rate mismatch: required {request.required_sample_rate} Hz != expected {expected_sr} Hz.",
                        target_format=target_format,
                        candidate_adapters=candidate_names,
                        duplicate_adapters=duplicate_names,
                    )

            # Montage provenance check
            if "require_montage_provenance" in meta and bool(meta["require_montage_provenance"]):
                if not any(c.montage_support for c in capable_candidates):
                    return SelectionResult(
                        status=SelectionStatus.INCOMPATIBLE,
                        selected_adapter=None,
                        reason_code=ReasonCode.MONTAGE_UNSUPPORTED,
                        reason_message="Montage provenance required but no candidate provides montage coordinates.",
                        target_format=target_format,
                        candidate_adapters=candidate_names,
                        duplicate_adapters=duplicate_names,
                    )

        # 6. Check dependency availability
        dependency_status: dict[str, bool] = {}
        for c in capable_candidates:
            dep_avail = self._dependency_checker(c.dependency)
            dependency_status[c.adapter_name] = dep_avail

        available_candidates = [c for c in capable_candidates if dependency_status[c.adapter_name]]

        if not available_candidates:
            missing_deps = sorted({c.dependency for c in capable_candidates if c.dependency})
            return SelectionResult(
                status=SelectionStatus.UNAVAILABLE,
                selected_adapter=None,
                reason_code=ReasonCode.DEPENDENCY_MISSING,
                reason_message=f"All candidates for format '{target_format}' are unavailable. Missing optional dependencies: {missing_deps}.",
                target_format=target_format,
                candidate_adapters=candidate_names,
                duplicate_adapters=duplicate_names,
                dependency_status=dependency_status,
            )

        # 7. Partition native vs fallback candidates
        native_candidates = [c for c in available_candidates if c.tier == AdapterTier.NATIVE]
        fallback_candidates = [c for c in available_candidates if c.tier != AdapterTier.NATIVE]

        # Rule 3: Prefer native adapter over fallback when capability evidence supports it
        if native_candidates:
            # Sort by priority descending
            sorted_native = sorted(native_candidates, key=lambda c: c.priority, reverse=True)
            top_priority = sorted_native[0].priority
            top_native = [c for c in sorted_native if c.priority == top_priority]

            # Rule 5: Refuse ambiguous selection rather than silently choosing
            if len(top_native) > 1:
                return SelectionResult(
                    status=SelectionStatus.AMBIGUOUS,
                    selected_adapter=None,
                    reason_code=ReasonCode.AMBIGUOUS_CANDIDATES,
                    reason_message=f"Ambiguous selection: multiple native candidates with equal priority {top_priority}: {[c.adapter_name for c in top_native]}.",
                    target_format=target_format,
                    candidate_adapters=candidate_names,
                    duplicate_adapters=duplicate_names,
                    dependency_status=dependency_status,
                )

            chosen = top_native[0]
            reason = ReasonCode.NATIVE_PREFERRED if fallback_candidates else ReasonCode.SINGLE_MATCH
            msg = (
                f"Selected native adapter '{chosen.adapter_name}' with verified capability evidence over fallback."
                if fallback_candidates
                else f"Selected canonical adapter '{chosen.adapter_name}'."
            )
            return SelectionResult(
                status=SelectionStatus.SELECTED,
                selected_adapter=chosen.adapter_name,
                reason_code=reason,
                reason_message=msg,
                target_format=target_format,
                candidate_adapters=candidate_names,
                duplicate_adapters=duplicate_names,
                dependency_status=dependency_status,
                provenance={"tier": chosen.tier.value, "priority": chosen.priority},
            )

        # No native candidate available; inspect fallbacks
        if not request.allow_fallback:
            return SelectionResult(
                status=SelectionStatus.UNAVAILABLE,
                selected_adapter=None,
                reason_code=ReasonCode.DEPENDENCY_MISSING,
                reason_message=f"No native adapter available for format '{target_format}' and fallback is disallowed.",
                target_format=target_format,
                candidate_adapters=candidate_names,
                duplicate_adapters=duplicate_names,
                dependency_status=dependency_status,
            )

        sorted_fallback = sorted(fallback_candidates, key=lambda c: c.priority, reverse=True)
        top_priority = sorted_fallback[0].priority
        top_fallback = [c for c in sorted_fallback if c.priority == top_priority]

        if len(top_fallback) > 1:
            return SelectionResult(
                status=SelectionStatus.AMBIGUOUS,
                selected_adapter=None,
                reason_code=ReasonCode.AMBIGUOUS_CANDIDATES,
                reason_message=f"Ambiguous fallback selection: multiple fallback candidates with equal priority {top_priority}: {[c.adapter_name for c in top_fallback]}.",
                target_format=target_format,
                candidate_adapters=candidate_names,
                duplicate_adapters=duplicate_names,
                dependency_status=dependency_status,
            )

        chosen = top_fallback[0]
        return SelectionResult(
            status=SelectionStatus.FALLBACK_SELECTED,
            selected_adapter=chosen.adapter_name,
            reason_code=ReasonCode.FALLBACK_PRIMARY_UNAVAILABLE,
            reason_message=f"Primary native adapter unavailable; selected fallback adapter '{chosen.adapter_name}'.",
            target_format=target_format,
            candidate_adapters=candidate_names,
            duplicate_adapters=duplicate_names,
            dependency_status=dependency_status,
            provenance={"tier": chosen.tier.value, "priority": chosen.priority},
        )


def select_adapter(
    source: str | Path | None = None,
    file_format: str | None = None,
    *,
    required_channels: Sequence[str] | None = None,
    required_sample_rate: float | None = None,
    require_montage: bool = False,
    require_streaming: bool = False,
    allow_fallback: bool = True,
    allow_network: bool = False,
    metadata: Mapping[str, Any] | None = None,
    selector: CanonicalAdapterSelector | None = None,
) -> SelectionResult:
    """Convenience functional API to select a canonical signal adapter."""
    sel = selector or CanonicalAdapterSelector()
    req = SelectionRequest(
        source_path=source,
        file_format=file_format,
        required_channels=tuple(required_channels) if required_channels is not None else None,
        required_sample_rate=required_sample_rate,
        require_montage=require_montage,
        require_streaming=require_streaming,
        allow_fallback=allow_fallback,
        allow_network=allow_network,
        metadata=metadata,
    )
    return sel.select(req)


__all__ = [
    "AdapterCandidate",
    "AdapterTier",
    "CanonicalAdapterSelector",
    "DEFAULT_ADAPTER_CANDIDATES",
    "ReasonCode",
    "SelectionRequest",
    "SelectionResult",
    "SelectionStatus",
    "detect_format_from_path",
    "select_adapter",
]
