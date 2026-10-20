"""Wrapper around ``mne.preprocessing.compute_current_source_density``.

Engineering adapter only: explicit parameters, fail-closed preconditions,
and provenance. Not a scientific claim about neural mechanism or consciousness.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from .constants import (
    DEFAULT_COPY,
    DEFAULT_LAMBDA2,
    DEFAULT_N_LEGENDRE_TERMS,
    DEFAULT_SPHERE,
    DEFAULT_STIFFNESS,
    SUPPORTED_MNE_MIN_VERSION,
)
from .errors import CSDAdapterError, InvalidChannelSelectionError, MNEUnavailableError
from .preconditions import (
    excluded_channels,
    extract_channel_inventory,
    reject_reference_mutation,
    resolve_coordinate_frame,
    validate_channel_selection,
)
from .provenance import CSDProvenance, build_provenance, documented_output_units


def mne_available() -> bool:
    try:
        import mne  # noqa: F401
    except Exception:
        return False
    return True


def get_mne_version() -> Optional[str]:
    try:
        import mne
    except Exception:
        return None
    return getattr(mne, "__version__", None)


def _normalize_sphere(
    sphere: Union[str, Sequence[float]],
) -> Union[str, Tuple[float, float, float, float]]:
    if isinstance(sphere, str):
        if sphere != "auto":
            raise CSDAdapterError(
                f"unsupported sphere string {sphere!r}; use 'auto' or (x, y, z, r) meters"
            )
        return sphere
    try:
        vals = tuple(float(v) for v in sphere)
    except (TypeError, ValueError) as exc:
        raise CSDAdapterError(
            "sphere must be 'auto' or (x, y, z, r) with finite float meters"
        ) from exc
    if len(vals) != 4:
        raise CSDAdapterError("sphere must be (x, y, z, r) in meters")
    if not all(math.isfinite(v) for v in vals):
        raise CSDAdapterError(
            f"sphere components must be finite floats (meters); got {vals!r}"
        )
    if vals[3] <= 0:
        raise CSDAdapterError("sphere radius must be positive (meters)")
    return (vals[0], vals[1], vals[2], vals[3])


def _pick_instance(inst: Any, channels: Sequence[str], *, copy: bool) -> Any:
    """Return an instance restricted to ``channels`` without inventing montages.

    When ``copy`` is True, refuse to pick in-place if ``inst.copy()`` is missing
    or fails — callers must not be mutated as a side effect of channel selection.
    """
    if copy:
        if not hasattr(inst, "copy"):
            raise CSDAdapterError(
                "instance has no copy(); refusing in-place pick that would "
                "mutate the caller"
            )
        try:
            working = inst.copy()
        except Exception as exc:
            raise CSDAdapterError(
                f"instance.copy() failed; refusing to mutate caller: {exc}"
            ) from exc
    else:
        working = inst
    if hasattr(working, "pick"):
        try:
            working.pick(list(channels))
            return working
        except Exception as exc:
            raise InvalidChannelSelectionError(
                f"failed to pick explicit channels {list(channels)}: {exc}"
            ) from exc
    if hasattr(working, "pick_channels"):
        try:
            working.pick_channels(list(channels), ordered=True)
            return working
        except Exception as exc:
            raise InvalidChannelSelectionError(
                f"failed to pick_channels {list(channels)}: {exc}"
            ) from exc
    # Duck-typed test double: expose ch_names already equal to selection.
    names = list(getattr(working, "ch_names", []) or [])
    if names == list(channels):
        return working
    raise InvalidChannelSelectionError(
        "instance does not support pick/pick_channels and ch_names do not "
        "exactly match the explicit channel selection"
    )


def _infer_input_units(inst: Any, channels: Sequence[str]) -> Optional[str]:
    info = getattr(inst, "info", {}) or {}
    chs = info.get("chs") if isinstance(info, dict) else None
    if not isinstance(chs, Sequence):
        return None
    units = []
    name_to_ch = {}
    for ch in chs:
        if isinstance(ch, dict) and "ch_name" in ch:
            name_to_ch[ch["ch_name"]] = ch
    for name in channels:
        ch = name_to_ch.get(name)
        if not ch:
            continue
        unit = ch.get("unit")
        if unit is not None:
            units.append(str(unit))
    if not units:
        return None
    if len(set(units)) == 1:
        return units[0]
    return "mixed:" + ",".join(sorted(set(units)))


def _read_output_units(inst: Any, channels: Sequence[str]) -> Tuple[Optional[str], str, Optional[str]]:
    """Prefer runtime channel units; fall back to documented V/m^2 status."""
    documented, status, source = documented_output_units()
    info = getattr(inst, "info", {}) or {}
    chs = info.get("chs") if isinstance(info, dict) else None
    if not isinstance(chs, Sequence):
        return documented, status, source
    runtime = []
    for ch in chs:
        if not isinstance(ch, dict):
            continue
        if ch.get("ch_name") not in channels:
            continue
        unit = ch.get("unit")
        # MNE uses FIFF_UNIT_V_M2 integer; also accept string forms.
        if unit is None:
            continue
        runtime.append(str(unit))
    if not runtime:
        return documented, status, source
    # If runtime units disagree, do not claim a known physical unit.
    if len(set(runtime)) != 1:
        return None, "unknown", "runtime channel units disagree"
    # Prefer documented label when FIFF V/m^2 matches.
    try:
        from mne.io.constants import FIFF  # type: ignore

        if str(runtime[0]) == str(FIFF.FIFF_UNIT_V_M2):
            return documented, "documented", source
    except Exception:
        pass
    if runtime[0] in {documented, "V/m^2", "V/m2", "FIFF_UNIT_V_M2"}:
        return documented, "documented", source
    # Unknown mapping — do not invent a label.
    return None, "unknown", f"runtime unit token {runtime[0]!r} not mapped"


@dataclass
class CSDResult:
    """CSD transform result with explicit provenance."""

    instance: Any
    provenance: CSDProvenance
    data: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provenance": self.provenance.to_dict(),
            "has_instance": self.instance is not None,
            "has_data": self.data is not None,
        }


def inspect_preconditions(
    inst: Any,
    channels: Sequence[str],
    *,
    alter_reference: bool = False,
) -> Dict[str, Any]:
    """Validate inputs without applying CSD (works without MNE CSD call)."""
    reject_reference_mutation(alter_reference=alter_reference)
    inventory = extract_channel_inventory(inst)
    selected, reports, _ = validate_channel_selection(inventory, channels)
    excluded = excluded_channels(inventory, selected)
    return {
        "channels_selected": selected,
        "channels_excluded": excluded,
        "coordinate_frame": resolve_coordinate_frame(inst),
        "reports": [r.__dict__ for r in reports],
        "channel_types_requested": {r.name: r.ch_type for r in reports},
        "coordinates_m": {
            r.name: r.xyz_m for r in reports if r.xyz_m is not None
        },
    }


def apply_csd(
    inst: Any,
    channels: Sequence[str],
    *,
    sphere: Union[str, Sequence[float]] = DEFAULT_SPHERE,
    lambda2: float = DEFAULT_LAMBDA2,
    stiffness: float = DEFAULT_STIFFNESS,
    n_legendre_terms: int = DEFAULT_N_LEGENDRE_TERMS,
    copy: bool = DEFAULT_COPY,
    alter_reference: bool = False,
    verbose: Optional[Any] = "ERROR",
    csd_callable: Any = None,
) -> CSDResult:
    """Apply MNE CSD with explicit channel selection and recorded parameters.

    Parameters
    ----------
    inst:
        MNE Raw / Epochs / Evoked (or test double).
    channels:
        Explicit channel names to transform. Required — no silent heuristics.
    sphere, lambda2, stiffness, n_legendre_terms, copy:
        Forwarded to ``mne.preprocessing.compute_current_source_density``.
        Defaults match the documented MNE API.
    alter_reference:
        Must remain False. The adapter refuses to call ``set_eeg_reference``.
    csd_callable:
        Optional injectable backend (for tests). Defaults to MNE's function.

    Returns
    -------
    CSDResult
        Transformed instance plus provenance. ``transform_kind`` is sensor-space
        CSD / surface Laplacian, not anatomical source localization.
    """
    reject_reference_mutation(alter_reference=alter_reference)
    sphere_norm = _normalize_sphere(sphere)
    if lambda2 < 0 or lambda2 >= 1:
        raise CSDAdapterError("lambda2 must satisfy 0 <= lambda2 < 1 (MNE API)")
    if stiffness < 0:
        raise CSDAdapterError("stiffness must be non-negative (MNE API)")
    if int(n_legendre_terms) < 1:
        raise CSDAdapterError("n_legendre_terms must be >= 1")

    inventory = extract_channel_inventory(inst)
    selected, reports, _ = validate_channel_selection(inventory, channels)
    excluded = excluded_channels(inventory, selected)
    # Channels present on the instance but not selected are reported, not hidden.
    dropped_report = list(excluded)

    params = {
        "sphere": sphere_norm if isinstance(sphere_norm, str) else list(sphere_norm),
        "lambda2": float(lambda2),
        "stiffness": float(stiffness),
        "n_legendre_terms": int(n_legendre_terms),
        "copy": bool(copy),
        "verbose": verbose,
    }

    if csd_callable is None:
        if not mne_available():
            raise MNEUnavailableError(
                f"MNE is not installed; optional EEG profile requires mne>={SUPPORTED_MNE_MIN_VERSION}"
            )
        import mne

        csd_callable = mne.preprocessing.compute_current_source_density

    # Restrict to explicit selection before transform so non-selected channels
    # are not silently included. Selection is reported in provenance.
    picked = _pick_instance(inst, selected, copy=True)
    # MNE's own copy flag still applies to the CSD call on the picked instance.
    transformed = csd_callable(
        picked,
        sphere=sphere_norm,
        lambda2=float(lambda2),
        stiffness=float(stiffness),
        n_legendre_terms=int(n_legendre_terms),
        copy=bool(copy),
        verbose=verbose,
    )

    # Preserve / verify channel order against the explicit selection.
    out_names = list(getattr(transformed, "ch_names", []) or [])
    if out_names != list(selected):
        # Fail closed on reordering or silent drops.
        raise InvalidChannelSelectionError(
            f"CSD output channel order/membership mismatch: "
            f"selected={list(selected)} output={out_names}"
        )

    output_units, units_status, units_source = _read_output_units(transformed, selected)
    data = None
    if hasattr(transformed, "get_data"):
        try:
            data = transformed.get_data()
        except Exception:
            data = None

    warnings: List[str] = []
    if units_status != "documented":
        warnings.append(
            "output units are not established as a known physical label for this "
            "backend/version response; unit field left unknown"
        )

    provenance = build_provenance(
        mne_version=get_mne_version(),
        # Record real package presence only; an injected csd_callable must not
        # claim MNE is installed.
        mne_available=mne_available(),
        parameters=params,
        channel_types_requested={r.name: r.ch_type for r in reports},
        channels_selected=selected,
        channels_excluded=excluded,
        channels_dropped_report=dropped_report,
        coordinate_frame=resolve_coordinate_frame(inst),
        coordinates_m={r.name: r.xyz_m for r in reports if r.xyz_m is not None},
        sphere_model=sphere_norm,
        input_units=_infer_input_units(inst, selected),
        output_units=output_units,
        output_units_status=units_status,
        output_units_source=units_source,
        channel_order=out_names,
        warnings=warnings,
    )
    return CSDResult(instance=transformed, provenance=provenance, data=data)
