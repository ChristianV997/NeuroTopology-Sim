"""Convert in-memory fixtures or optional MNE objects to canonical blocks."""

from __future__ import annotations

import copy
import hashlib
import math
import numbers
from typing import Any, Mapping, Sequence

from adapters.mne_signal_blocks.reporting import fingerprint_mapping, serialize_json
from adapters.mne_signal_blocks.schema import (
    SCHEMA_VERSION,
    BlockStatus,
    CanonicalInMemorySignalBlock,
    ConversionResult,
    ReasonCode,
)
from adapters.mne_signal_blocks.validate import validate_block_fields


def _probe_mne() -> tuple[bool, str | None]:
    try:
        import mne

        return True, getattr(mne, "__version__", None)
    except Exception:
        return False, None


def _copy_data(data: Any) -> Any:
    if data is None:
        return None
    try:
        import numpy as np

        arr = np.asarray(data)
        return np.array(arr, copy=True)
    except Exception:
        return copy.deepcopy(data)


def _fingerprint_input(payload: Mapping[str, Any], data: Any) -> str:
    meta = {k: v for k, v in payload.items() if k != "data"}

    def finite_fingerprint_value(value: Any) -> Any:
        if isinstance(value, float) and not math.isfinite(value):
            return {"__non_finite_float__": repr(value)}
        if isinstance(value, Mapping):
            return {str(key): finite_fingerprint_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [finite_fingerprint_value(item) for item in value]
        return value

    digest = hashlib.sha256()
    digest.update(serialize_json(finite_fingerprint_value(meta), indent=None).encode("utf-8"))
    if data is not None:
        try:
            import numpy as np

            arr = np.asarray(data)
            digest.update(arr.tobytes(order="C"))
            digest.update(str(arr.shape).encode("utf-8"))
            digest.update(str(arr.dtype).encode("utf-8"))
        except Exception:
            digest.update(repr(data).encode("utf-8"))
    return digest.hexdigest()


def _normalize_units(
    units: Any, n_channels: int
) -> tuple[str | None, ...]:
    if units is None:
        return tuple(None for _ in range(max(n_channels, 0)))
    if isinstance(units, str):
        token = units.strip() or None
        return tuple(token for _ in range(max(n_channels, 0)))
    if isinstance(units, (list, tuple)):
        out: list[str | None] = []
        for item in units:
            if item is None:
                out.append(None)
            elif not isinstance(item, str):
                out.append(None)
            else:
                text = item.strip()
                out.append(text or None)
        if len(out) == 1 and n_channels > 1:
            return tuple(out[0] for _ in range(n_channels))
        return tuple(out)
    return tuple(None for _ in range(max(n_channels, 0)))


def _normalize_sample_rate(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        return None
    try:
        rate = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return rate if math.isfinite(rate) and rate > 0 else None


def _is_sample_index(value: Any) -> bool:
    """Accept integral sample indices without accepting bools or coercible text."""
    return isinstance(value, numbers.Integral) and not isinstance(value, bool)


def _invalid_sample_bounds_result(
    *,
    source_id: str | None,
    source_sha256: str | None,
    mne_available: bool,
    mne_version: str | None,
) -> ConversionResult:
    """Return a fail-closed, value-redacted result for invalid bounds."""
    block = CanonicalInMemorySignalBlock(
        schema_version=SCHEMA_VERSION,
        status=BlockStatus.REJECTED,
        reason_codes=(ReasonCode.INVALID_SAMPLE_BOUNDS.value,),
        channel_names=(),
        channel_types=(),
        units=(),
        sample_rate_hz=None,
        time_origin=None,
        block_start_sample=None,
        block_end_sample=None,
        n_channels=0,
        n_samples=0,
        data_shape=(),
        bad_channels=(),
        events=(),
        annotations=(),
        reference=None,
        montage_name=None,
        montage_coordinates=None,
        preprocessing_history=(),
        source_id=source_id,
        source_sha256=source_sha256,
        checksum_state="unknown" if not source_sha256 else "declared",
        scientific_pass=False,
        data=None,
        warnings=(
            "sample bounds must be non-negative integer half-open bounds "
            "within the available sample range",
        ),
        mne_available=mne_available,
        mne_version=mne_version,
    )
    return ConversionResult(block=block, input_fingerprint="", mutated_input=False)


def convert_in_memory_block(
    payload: Mapping[str, Any],
    *,
    copy_data: bool = True,
    allow_channel_types: frozenset[str] | None = None,
) -> ConversionResult:
    """Convert a plain in-memory mapping (fixture or adapter output).

    Required shape when data is present: (n_channels, n_samples).
    Missing units/reference/montage remain explicit nulls and yield INCONCLUSIVE
    rather than invented defaults. Input mappings/arrays are not mutated.
    """
    if not isinstance(payload, Mapping):
        block = CanonicalInMemorySignalBlock(
            schema_version=SCHEMA_VERSION,
            status=BlockStatus.ERROR,
            reason_codes=(ReasonCode.MALFORMED_INPUT.value,),
            channel_names=(),
            channel_types=(),
            units=(),
            sample_rate_hz=None,
            time_origin=None,
            block_start_sample=None,
            block_end_sample=None,
            n_channels=0,
            n_samples=0,
            data_shape=(),
            bad_channels=(),
            events=(),
            annotations=(),
            reference=None,
            montage_name=None,
            montage_coordinates=None,
            preprocessing_history=(),
            source_id=None,
            source_sha256=None,
            checksum_state="unknown",
            scientific_pass=False,
            data=None,
            warnings=("payload must be a mapping",),
        )
        return ConversionResult(block=block, input_fingerprint="", mutated_input=False)

    original = copy.deepcopy(dict(payload))
    data_in = payload.get("data")
    data_out = _copy_data(data_in) if copy_data else data_in
    raw_names = payload.get("channel_names")
    channel_names = (
        tuple(name if isinstance(name, str) else "" for name in raw_names)
        if isinstance(raw_names, (list, tuple))
        else ()
    )
    raw_types = payload.get("channel_types")
    if raw_types is None:
        channel_types: tuple[str | None, ...] = tuple(None for _ in channel_names)
    elif isinstance(raw_types, (list, tuple)):
        channel_types = tuple(
            None if item is None else str(item).strip().lower() or None for item in raw_types
        )
    else:
        channel_types = ()
    n_channels = len(channel_names)
    units = _normalize_units(payload.get("units"), n_channels)

    status, reasons, warnings = validate_block_fields(
        channel_names=channel_names,
        channel_types=channel_types,
        units=units,
        sample_rate_hz=payload.get("sample_rate_hz"),
        data=data_out,
        events=payload.get("events"),
        allow_channel_types=allow_channel_types,
        reference=payload.get("reference"),
        montage_name=payload.get("montage_name"),
        montage_coordinates=payload.get("montage_coordinates"),
        block_start_sample=payload.get("block_start_sample"),
        block_end_sample=payload.get("block_end_sample"),
    )

    reasons = list(reasons)
    warnings = list(warnings)

    reference = payload.get("reference")
    if not isinstance(reference, str) or not reference.strip():
        reference = None
        if ReasonCode.MISSING_REFERENCE.value not in reasons and status != BlockStatus.REJECTED:
            reasons.append(ReasonCode.MISSING_REFERENCE.value)
            if status == BlockStatus.CONVERTED:
                status = BlockStatus.INCONCLUSIVE

    montage_name = payload.get("montage_name")
    if not isinstance(montage_name, str) or not montage_name.strip():
        montage_name = None
    montage_coordinates = payload.get("montage_coordinates")
    if ReasonCode.MISSING_MONTAGE.value in reasons and status != BlockStatus.REJECTED:
        warnings.append("montage absent or incomplete; left unknown")

    # Deduplicate reasons; drop OK once soft/hard codes are present
    reasons = list(dict.fromkeys(reasons))
    if status != BlockStatus.CONVERTED and ReasonCode.OK.value in reasons:
        reasons = [code for code in reasons if code != ReasonCode.OK.value]
    if status == BlockStatus.CONVERTED and any(
        code != ReasonCode.OK.value for code in reasons
    ):
        status = BlockStatus.INCONCLUSIVE
        reasons = [code for code in reasons if code != ReasonCode.OK.value]

    shape = ()
    n_samples = 0
    if data_out is None:
        # Absent signal cannot be CONVERTED: producer would disagree with
        # validate_block, which requires a 2-D shape when data is omitted.
        if ReasonCode.SHAPE_MISMATCH.value not in reasons:
            reasons.append(ReasonCode.SHAPE_MISMATCH.value)
        warnings.append(
            "signal data absent; incomplete block cannot be marked converted"
        )
        if status in {BlockStatus.CONVERTED, BlockStatus.INCONCLUSIVE}:
            status = BlockStatus.REJECTED
        if ReasonCode.OK.value in reasons:
            reasons = [code for code in reasons if code != ReasonCode.OK.value]
    else:
        try:
            import numpy as np

            shape = tuple(int(x) for x in np.asarray(data_out).shape)
        except Exception:
            if isinstance(data_out, (list, tuple)) and data_out and isinstance(data_out[0], (list, tuple)):
                shape = (len(data_out), len(data_out[0]))
            elif isinstance(data_out, (list, tuple)):
                shape = (len(data_out),)
        if len(shape) == 2:
            n_channels = shape[0]
            n_samples = shape[1]

    raw_events = payload.get("events")
    events = (
        tuple(dict(item) for item in raw_events if isinstance(item, Mapping))
        if isinstance(raw_events, (list, tuple))
        else ()
    )
    annotations = tuple(
        dict(item) for item in (payload.get("annotations") or ()) if isinstance(item, Mapping)
    )
    bad_channels = tuple(str(x) for x in (payload.get("bad_channels") or ()))
    history = tuple(str(x) for x in (payload.get("preprocessing_history") or ()))

    source_sha = payload.get("source_sha256")
    if source_sha is None or source_sha == "":
        checksum_state = "unknown"
        source_sha = None
    else:
        checksum_state = "declared"

    coords_out = None
    if montage_coordinates is not None:
        try:
            coordinate_rows = list(montage_coordinates)
        except TypeError:
            coordinate_rows = None
        if coordinate_rows is not None:
            coords_out = []
            for row in coordinate_rows:
                if row is None or not isinstance(row, (list, tuple)) or len(row) != 3:
                    coords_out.append(None)
                else:
                    try:
                        point = (float(row[0]), float(row[1]), float(row[2]))
                        coords_out.append(point if all(math.isfinite(value) for value in point) else None)
                    except (TypeError, ValueError, OverflowError):
                        coords_out.append(None)
            coords_out = tuple(coords_out)

    mne_ok, mne_ver = _probe_mne()
    block = CanonicalInMemorySignalBlock(
        schema_version=SCHEMA_VERSION,
        status=status,
        reason_codes=tuple(reasons),
        channel_names=channel_names,
        channel_types=channel_types if channel_types else tuple(None for _ in channel_names),
        units=units,
        sample_rate_hz=_normalize_sample_rate(payload.get("sample_rate_hz")),
        time_origin=payload.get("time_origin"),
        block_start_sample=payload.get("block_start_sample"),
        block_end_sample=payload.get("block_end_sample"),
        n_channels=n_channels,
        n_samples=n_samples,
        data_shape=shape,
        bad_channels=bad_channels,
        events=events,
        annotations=annotations,
        reference=str(reference) if reference is not None else None,
        montage_name=str(montage_name) if montage_name not in (None, "") else None,
        montage_coordinates=coords_out,
        preprocessing_history=history,
        source_id=payload.get("source_id"),
        source_sha256=source_sha,
        checksum_state=checksum_state,
        scientific_pass=False,
        data=data_out,
        warnings=tuple(warnings),
        mne_available=mne_ok,
        mne_version=mne_ver,
    )

    # Mutation check: payload mapping must equal deep-copied original metadata
    # (excluding data identity). We compare keys used for metadata.
    mutated = False
    for key, value in original.items():
        if key == "data":
            continue
        if payload.get(key) != value:
            mutated = True
            break

    fingerprint = _fingerprint_input(original, original.get("data"))
    if mutated:
        # Should never happen; surface as error if caller passed a mutable
        # mapping that another thread changed mid-flight.
        block = CanonicalInMemorySignalBlock(
            **{
                **block.metadata_dict(include_data=True),
                "status": BlockStatus.ERROR,
                "reason_codes": (ReasonCode.INPUT_MUTATION_FORBIDDEN.value,),
                "data": block.data,
            }
        )
    return ConversionResult(block=block, input_fingerprint=fingerprint, mutated_input=mutated)


def convert_from_mne_object(
    obj: Any,
    *,
    source_id: str | None = None,
    source_sha256: str | None = None,
    start_sample: int = 0,
    stop_sample: int | None = None,
    copy_data: bool = True,
) -> ConversionResult:
    """Optional MNE Raw/Epochs bridge.

    Reads declared Info fields only. Does not resample, filter, rereference,
    interpolate, reorder, or drop channels. Units are taken from channel
    metadata when present; otherwise left unknown (never defaulted to ``V``).
    """
    available, version = _probe_mne()
    # Validate caller-provided bounds before any coercion or object slicing.
    # NumPy integral scalars are accepted, while bools, floats, and numeric
    # strings must not be silently changed by int().
    if not _is_sample_index(start_sample) or (
        stop_sample is not None and not _is_sample_index(stop_sample)
    ):
        return _invalid_sample_bounds_result(
            source_id=source_id,
            source_sha256=source_sha256,
            mne_available=available,
            mne_version=version,
        )
    if not available:
        block = CanonicalInMemorySignalBlock(
            schema_version=SCHEMA_VERSION,
            status=BlockStatus.ERROR,
            reason_codes=(ReasonCode.MNE_UNAVAILABLE.value,),
            channel_names=(),
            channel_types=(),
            units=(),
            sample_rate_hz=None,
            time_origin=None,
            block_start_sample=None,
            block_end_sample=None,
            n_channels=0,
            n_samples=0,
            data_shape=(),
            bad_channels=(),
            events=(),
            annotations=(),
            reference=None,
            montage_name=None,
            montage_coordinates=None,
            preprocessing_history=(),
            source_id=source_id,
            source_sha256=source_sha256,
            checksum_state="unknown" if not source_sha256 else "declared",
            scientific_pass=False,
            data=None,
            warnings=("mne is not installed; use convert_in_memory_block with fixtures",),
            mne_available=False,
            mne_version=None,
        )
        return ConversionResult(block=block, input_fingerprint="", mutated_input=False)

    import mne

    n_times = getattr(obj, "n_times", None)
    if n_times is not None and not _is_sample_index(n_times):
        return _invalid_sample_bounds_result(
            source_id=source_id,
            source_sha256=source_sha256,
            mne_available=True,
            mne_version=version,
        )
    effective_stop = n_times if stop_sample is None else stop_sample
    if (
        start_sample < 0
        or (effective_stop is not None and effective_stop <= start_sample)
        or (
            n_times is not None
            and (
                start_sample >= n_times
                or (effective_stop is not None and effective_stop > n_times)
            )
        )
    ):
        return _invalid_sample_bounds_result(
            source_id=source_id,
            source_sha256=source_sha256,
            mne_available=True,
            mne_version=version,
        )

    # Coercion is now safe: validation established integral, in-range bounds.
    start_sample = int(start_sample)
    stop_sample = int(effective_stop) if effective_stop is not None else None

    info = getattr(obj, "info", None)
    if info is None:
        return convert_in_memory_block(
            {"source_id": source_id, "source_sha256": source_sha256, "data": None}
        )

    ch_names = list(info.get("ch_names") or [])
    chs = list(info.get("chs") or [])
    sfreq = info.get("sfreq")
    bads = list(info.get("bads") or [])

    # Channel types via MNE helper when present; otherwise leave unknown.
    try:
        channel_types = list(mne.channel_type(info, i) for i in range(len(ch_names)))
    except Exception:
        channel_types = [None for _ in ch_names]

    units: list[str | None] = []
    for idx, name in enumerate(ch_names):
        unit = None
        if idx < len(chs):
            # FIF unit codes are integers; without a verified mapping we do not
            # invent SI strings. Prefer explicit unit_mul/unit only when a
            # string unit was attached by the caller/fixture path.
            raw_unit = chs[idx].get("unit")
            if isinstance(raw_unit, str) and raw_unit.strip():
                unit = raw_unit.strip()
        units.append(unit)

    # Reference: custom_ref_applied is an int flag, not a named reference.
    # Without an explicit string we leave reference unknown.
    custom_ref = info.get("custom_ref_applied")
    reference = None
    if isinstance(custom_ref, str) and custom_ref.strip():
        reference = custom_ref.strip()

    meas_date = info.get("meas_date")
    time_origin = str(meas_date) if meas_date is not None else None

    # Data slice — Raw and Epochs both expose get_data/preload in modern MNE.
    # Distinguish by ndarray rank: 3D → Epochs (epoch 0 + time window); 2D with
    # __getitem__ → Raw-style slicing so start/stop bounds stay authoritative.
    data = None
    warnings_extra: list[str] = []
    payload_events: list[Any] = []
    try:
        import numpy as np

        if hasattr(obj, "get_data"):
            arr = np.asarray(obj.get_data())
            if arr.ndim == 3:
                warnings_extra.append(
                    "Epochs data is 3D; using epoch 0 only without averaging or concatenation"
                )
                epoch0 = arr[0]
                data = (
                    epoch0[:, start_sample:stop_sample]
                    if stop_sample is not None
                    else epoch0[:, start_sample:]
                )
            elif arr.ndim == 2 and hasattr(obj, "__getitem__"):
                picked = (
                    obj[:, start_sample:stop_sample]
                    if stop_sample is not None
                    else obj[:, start_sample:]
                )
                data = picked[0]
            elif arr.ndim == 2:
                data = (
                    arr[:, start_sample:stop_sample]
                    if stop_sample is not None
                    else arr[:, start_sample:]
                )
            else:
                warnings_extra.append(
                    f"unsupported get_data ndarray rank {arr.ndim}; expected 2 or 3"
                )
                data = None
        elif hasattr(obj, "__getitem__"):
            picked = (
                obj[:, start_sample:stop_sample]
                if stop_sample is not None
                else obj[:, start_sample:]
            )
            data = picked[0]
        else:
            warnings_extra.append("unsupported MNE object interface")
            data = None
    except Exception as exc:
        warnings_extra.append(f"mne data read failed: {exc}")
        payload_events = []
        data = None

    # Annotations if present
    annotations = []
    ann = getattr(obj, "annotations", None)
    if ann is not None:
        try:
            for onset, duration, desc in zip(ann.onset, ann.duration, ann.description):
                annotations.append(
                    {
                        "onset_s": float(onset),
                        "duration_s": float(duration),
                        "description": str(desc),
                    }
                )
        except Exception:
            warnings_extra.append("annotations present but unreadable; left empty")

    # Montage name if set
    montage_name = None
    try:
        montage = obj.get_montage() if hasattr(obj, "get_montage") else None
        if montage is not None:
            montage_name = getattr(montage, "kind", None) or type(montage).__name__
    except Exception:
        montage_name = None

    history = []
    for key in ("highpass", "lowpass"):
        value = info.get(key)
        if value is not None:
            history.append(f"info.{key}={value}")

    payload = {
        "channel_names": ch_names,
        "channel_types": channel_types,
        "units": units,
        "sample_rate_hz": (
            sfreq
            if isinstance(sfreq, bool)
            else float(sfreq)
            if isinstance(sfreq, numbers.Real)
            else None
        ),
        "time_origin": time_origin,
        "block_start_sample": start_sample,
        "block_end_sample": stop_sample,
        "bad_channels": bads,
        "events": payload_events,
        "annotations": annotations,
        "reference": reference,
        "montage_name": montage_name,
        "montage_coordinates": None,
        "preprocessing_history": history,
        "source_id": source_id or "mne-in-memory",
        "source_sha256": source_sha256,
        "data": data,
        "mne_version": version,
    }
    result = convert_in_memory_block(payload, copy_data=copy_data)
    if warnings_extra:
        meta = result.block.metadata_dict(include_data=True)
        meta["warnings"] = list(result.block.warnings) + warnings_extra
        meta["mne_available"] = True
        meta["mne_version"] = version
        # Rebuild frozen dataclass
        block = CanonicalInMemorySignalBlock(
            schema_version=meta["schema_version"],
            status=BlockStatus(meta["status"]),
            reason_codes=tuple(meta["reason_codes"]),
            channel_names=tuple(meta["channel_names"]),
            channel_types=tuple(meta["channel_types"]),
            units=tuple(meta["units"]),
            sample_rate_hz=meta["sample_rate_hz"],
            time_origin=meta["time_origin"],
            block_start_sample=meta["block_start_sample"],
            block_end_sample=meta["block_end_sample"],
            n_channels=meta["n_channels"],
            n_samples=meta["n_samples"],
            data_shape=tuple(meta["data_shape"]),
            bad_channels=tuple(meta["bad_channels"]),
            events=tuple(meta["events"]),
            annotations=tuple(meta["annotations"]),
            reference=meta["reference"],
            montage_name=meta["montage_name"],
            montage_coordinates=result.block.montage_coordinates,
            preprocessing_history=tuple(meta["preprocessing_history"]),
            source_id=meta["source_id"],
            source_sha256=meta["source_sha256"],
            checksum_state=meta["checksum_state"],
            scientific_pass=False,
            data=result.block.data,
            warnings=tuple(meta["warnings"]),
            mne_available=True,
            mne_version=version,
        )
        return ConversionResult(
            block=block,
            input_fingerprint=result.input_fingerprint,
            mutated_input=result.mutated_input,
        )
    return result
