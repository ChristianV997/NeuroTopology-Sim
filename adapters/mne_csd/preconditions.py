"""Pure precondition checks for CSD inputs (usable without calling MNE CSD)."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .errors import InvalidChannelSelectionError, MissingCoordinatesError, ReferenceMutationError
from .provenance import ChannelCoordinateReport

_ZERO_EPS = 1e-12


def _as_xyz(loc: Any) -> Optional[Tuple[float, float, float]]:
    try:
        vals = [float(loc[i]) for i in range(3)]
    except Exception:
        return None
    if all(abs(v) <= _ZERO_EPS for v in vals):
        return None
    return (vals[0], vals[1], vals[2])


def extract_channel_inventory(inst: Any) -> Dict[str, Dict[str, Any]]:
    """Build a name -> {ch_type, xyz_m, index} map from an MNE-like instance.

    Works with real MNE Raw/Epochs/Evoked or duck-typed test doubles exposing
    ``ch_names``, ``get_channel_types`` (optional), and ``info['chs']``.
    """
    names = list(getattr(inst, "ch_names", []) or [])
    if not names:
        raise InvalidChannelSelectionError("instance has no channel names")

    types: List[str]
    if hasattr(inst, "get_channel_types"):
        try:
            types = list(inst.get_channel_types())
        except Exception:
            types = ["unknown"] * len(names)
    else:
        types = []
        info = getattr(inst, "info", {}) or {}
        chs = info.get("chs") if isinstance(info, Mapping) else None
        if isinstance(chs, Sequence) and len(chs) == len(names):
            for ch in chs:
                kind = None
                if isinstance(ch, Mapping):
                    kind = ch.get("kind") or ch.get("ch_type") or ch.get("type")
                types.append(str(kind).lower() if kind is not None else "unknown")
        else:
            types = ["unknown"] * len(names)

    inventory: Dict[str, Dict[str, Any]] = {}
    info = getattr(inst, "info", {}) or {}
    chs = info.get("chs") if isinstance(info, Mapping) else None
    for index, name in enumerate(names):
        xyz = None
        if isinstance(chs, Sequence) and index < len(chs):
            ch = chs[index]
            loc = ch.get("loc") if isinstance(ch, Mapping) else None
            if loc is not None:
                xyz = _as_xyz(loc)
        ch_type = types[index] if index < len(types) else "unknown"
        # Normalize only exact scalp-EEG tokens. Substring matches such as
        # ``"eeg" in "seeg"`` would misclassify intracranial channels.
        normalized = str(ch_type).strip().casefold()
        if normalized in {"2", "eeg"}:
            ch_type = "eeg"
        else:
            ch_type = normalized
        inventory[name] = {"ch_type": ch_type, "xyz_m": xyz, "index": index}
    return inventory


def resolve_coordinate_frame(inst: Any) -> Optional[str]:
    info = getattr(inst, "info", {}) or {}
    if not isinstance(info, Mapping):
        return None
    for key in ("chs",):
        chs = info.get(key)
        if isinstance(chs, Sequence) and chs:
            ch0 = chs[0]
            if isinstance(ch0, Mapping):
                # MNE stores coord_frame on each channel dict.
                frame = ch0.get("coord_frame")
                if frame is not None:
                    return str(frame)
    dig = info.get("dig")
    if dig:
        return "digitization_present"
    return None


def validate_channel_selection(
    inventory: Mapping[str, Mapping[str, Any]],
    channels: Sequence[str],
    *,
    require_eeg: bool = True,
) -> Tuple[List[str], List[ChannelCoordinateReport], List[str]]:
    """Validate an explicit channel list. Returns (selected, reports, errors)."""
    if not channels:
        raise InvalidChannelSelectionError(
            "channels must be an explicit non-empty sequence; "
            "silent channel heuristics are not allowed"
        )
    selected: List[str] = []
    reports: List[ChannelCoordinateReport] = []
    errors: List[str] = []
    seen = set()
    for name in channels:
        if name in seen:
            errors.append(f"duplicate channel selection: {name}")
            continue
        seen.add(name)
        meta = inventory.get(name)
        if meta is None:
            errors.append(f"channel not found: {name}")
            reports.append(
                ChannelCoordinateReport(name, "missing", None, False, "not_found")
            )
            continue
        ch_type = str(meta.get("ch_type", "unknown"))
        xyz = meta.get("xyz_m")
        usable = True
        reason = None
        if require_eeg and ch_type != "eeg":
            usable = False
            reason = f"non_eeg_type:{ch_type}"
            errors.append(f"channel {name} has type {ch_type!r}; CSD requires eeg")
        if xyz is None:
            usable = False
            reason = reason or "missing_or_zero_xyz"
            errors.append(f"channel {name} lacks usable 3D coordinates (meters)")
        reports.append(
            ChannelCoordinateReport(
                name=name,
                ch_type=ch_type,
                xyz_m=None if xyz is None else (float(xyz[0]), float(xyz[1]), float(xyz[2])),
                usable=usable,
                reason=reason,
            )
        )
        if usable:
            selected.append(name)
    if errors:
        # Prefer MissingCoordinatesError when that is the only class of failure.
        only_coords = all("lacks usable 3D coordinates" in e for e in errors)
        msg = "; ".join(errors)
        if only_coords:
            raise MissingCoordinatesError(msg)
        raise InvalidChannelSelectionError(msg)
    return selected, reports, errors


def excluded_channels(
    inventory: Mapping[str, Mapping[str, Any]],
    selected: Iterable[str],
) -> List[str]:
    selected_set = set(selected)
    return [name for name in inventory if name not in selected_set]


def reject_reference_mutation(*, alter_reference: bool) -> None:
    """The adapter never silently changes the EEG reference before CSD."""
    if alter_reference:
        raise ReferenceMutationError(
            "alter_reference=True is refused: the adapter must not call "
            "set_eeg_reference or otherwise mutate the reference. MNE CSD is "
            "itself documented as a reference-free Laplacian transform."
        )


def require_finite_array(data: Any, *, label: str = "data") -> None:
    import math

    if data is None:
        raise InvalidChannelSelectionError(f"{label} is None")
    # Support nested sequences without numpy.
    stack = [data]
    while stack:
        cur = stack.pop()
        if isinstance(cur, (list, tuple)):
            stack.extend(cur)
            continue
        try:
            value = float(cur)
        except Exception as exc:
            raise InvalidChannelSelectionError(f"{label} is not numeric") from exc
        if not math.isfinite(value):
            raise InvalidChannelSelectionError(f"{label} contains non-finite values")
