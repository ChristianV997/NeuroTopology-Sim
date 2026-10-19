"""Boundary conformance checker for inter-stage synthetic pipeline artifacts.

Enforces zero silent coercion:
- Never coerces or transposes shapes silently.
- Never re-sorts or permutes channels to match expectations.
- Never fills missing units, sampling rates, or timestamps with implicit defaults.
- Rejects non-finite values (NaN, Inf) fail-closed.
- Rejects stale or unsupported schema versions.
"""
from __future__ import annotations

import importlib
import math
from typing import Any, Mapping, Sequence

import numpy as np

from .contracts import BoundaryReport, BoundaryStatus


def check_shape_conformance(
    expected_shape: Sequence[int] | None,
    observed_shape: Sequence[int] | None,
) -> list[str]:
    """Verify that observed array shape matches expected shape without silent transposition."""
    mismatches: list[str] = []
    if expected_shape is None:
        return mismatches
    if observed_shape is None:
        mismatches.append(f"Expected shape {list(expected_shape)} but observed shape is None")
        return mismatches

    if list(expected_shape) != list(observed_shape):
        mismatches.append(
            f"Shape mismatch: expected {list(expected_shape)}, observed {list(observed_shape)}"
        )
    return mismatches


def check_channel_ordering_conformance(
    expected_channels: Sequence[str] | None,
    observed_channels: Sequence[str] | None,
) -> list[str]:
    """Verify channel ordering bit-for-bit without silent sorting or re-indexing."""
    mismatches: list[str] = []
    if expected_channels is None:
        return mismatches
    if observed_channels is None:
        mismatches.append(
            f"Expected channel ordering {list(expected_channels)} but observed channels is None"
        )
        return mismatches

    exp_list = list(expected_channels)
    obs_list = list(observed_channels)

    if exp_list != obs_list:
        if set(exp_list) == set(obs_list):
            mismatches.append(
                f"Channel ordering mismatch (permuting channels is forbidden): "
                f"expected {exp_list}, observed {obs_list}"
            )
        else:
            diff_exp = [c for c in exp_list if c not in obs_list]
            diff_obs = [c for c in obs_list if c not in exp_list]
            mismatches.append(
                f"Channel set mismatch: missing in observed {diff_exp}, unexpected in observed {diff_obs}"
            )
    return mismatches


def check_unit_conformance(
    expected_units: str | Sequence[str] | None,
    observed_units: str | Sequence[str] | None,
) -> list[str]:
    """Verify physical/calibration units without silent numerical scaling."""
    mismatches: list[str] = []
    if expected_units is None or expected_units == "":
        return mismatches
    if observed_units is None or observed_units == "" or observed_units == "unknown":
        mismatches.append(
            f"Unit missing or unknown: expected {expected_units}, observed {observed_units}"
        )
        return mismatches

    if isinstance(expected_units, str) and isinstance(observed_units, str):
        if expected_units.strip().lower() != observed_units.strip().lower():
            mismatches.append(
                f"Unit mismatch: expected '{expected_units}', observed '{observed_units}'"
            )
    elif isinstance(expected_units, (list, tuple)) and isinstance(observed_units, (list, tuple)):
        if list(expected_units) != list(observed_units):
            mismatches.append(
                f"Per-channel unit mismatch: expected {list(expected_units)}, observed {list(observed_units)}"
            )
    else:
        # String vs list
        exp_str = expected_units if isinstance(expected_units, str) else expected_units[0]
        obs_str = observed_units if isinstance(observed_units, str) else observed_units[0]
        if exp_str.strip().lower() != obs_str.strip().lower():
            mismatches.append(
                f"Unit format mismatch: expected '{expected_units}', observed '{observed_units}'"
            )
    return mismatches


def check_timing_conformance(
    expected_rate_hz: float | None,
    observed_rate_hz: float | None,
    sample_count: int | None = None,
    timestamps: Any | None = None,
    require_timestamps: bool = False,
) -> tuple[list[str], list[str]]:
    """Verify timing metadata: sampling rate positivity, consistency, and strictly increasing timestamps.

    Distinguishes:
    - Absent timestamps: when require_timestamps is True and timestamps is None or empty.
    - Malformed timestamps: when timestamps are present but non-1D, non-finite, non-monotonic,
      inconsistent in count with sample_count, or step inconsistent with sampling_rate_hz.
    """
    mismatches: list[str] = []
    missing_fields: list[str] = []

    if expected_rate_hz is not None:
        if observed_rate_hz is None:
            missing_fields.append("sampling_rate_hz")
        else:
            try:
                obs_f = float(observed_rate_hz)
                if not math.isfinite(obs_f) or obs_f <= 0:
                    mismatches.append(f"Non-positive or non-finite sampling rate: {observed_rate_hz}")
                elif abs(float(expected_rate_hz) - obs_f) > 1e-6:
                    mismatches.append(
                        f"Sampling rate mismatch: expected {expected_rate_hz} Hz, observed {obs_f} Hz"
                    )
            except (TypeError, ValueError):
                mismatches.append(f"Invalid sampling rate value: {observed_rate_hz}")

    if require_timestamps:
        if timestamps is None:
            missing_fields.append("timestamps")
            mismatches.append("Timing contract requires timestamps, but timestamps are absent (None)")
        elif hasattr(timestamps, "__len__") and len(timestamps) == 0:
            missing_fields.append("timestamps")
            mismatches.append("Timing contract requires timestamps, but timestamps array is empty")

    if timestamps is not None and not (hasattr(timestamps, "__len__") and len(timestamps) == 0):
        ts_arr = np.asarray(timestamps)
        if ts_arr.ndim != 1:
            mismatches.append(f"Malformed timestamps: must be 1D, observed {ts_arr.ndim}D")
        else:
            if not np.all(np.isfinite(ts_arr)):
                mismatches.append("Malformed timestamps: contain non-finite values (NaN/Inf)")
            if len(ts_arr) > 1 and not bool(np.all(np.diff(ts_arr) > 0)):
                mismatches.append("Malformed timestamps: not strictly monotonically increasing")
            if sample_count is not None and len(ts_arr) != sample_count:
                mismatches.append(
                    f"Malformed timestamps: timestamp count ({len(ts_arr)}) does not match sample count ({sample_count})"
                )
            if observed_rate_hz is not None and len(ts_arr) > 1:
                try:
                    obs_f = float(observed_rate_hz)
                    if obs_f > 0:
                        expected_dt = 1.0 / obs_f
                        dt_diffs = np.diff(ts_arr)
                        if np.all(np.isfinite(dt_diffs)):
                            mean_dt = float(np.mean(dt_diffs))
                            if abs(mean_dt - expected_dt) > 1e-4:
                                mismatches.append(
                                    f"Malformed timestamps: mean sampling step ({mean_dt:.6f} s) does not match declared rate {obs_f} Hz ({expected_dt:.6f} s)"
                                )
                except Exception:
                    pass

    return mismatches, missing_fields


def check_coordinate_conformance(
    coordinates: Any | None,
    channel_count: int | None,
    coordinate_status: str | None = None,
) -> list[str]:
    """Verify montage coordinate dimensions, alignment, and absence of NaN/Inf."""
    mismatches: list[str] = []
    if coordinates is None:
        if coordinate_status in ("3d_montage", "2d_planar"):
            mismatches.append(
                f"Declared coordinate status is '{coordinate_status}' but coordinate data is None"
            )
        return mismatches

    coord_arr = np.asarray(coordinates)
    if coord_arr.ndim != 2 or coord_arr.shape[1] not in (2, 3):
        mismatches.append(
            f"Coordinates must have shape (n_channels, 2) or (n_channels, 3), observed {coord_arr.shape}"
        )
    elif channel_count is not None and coord_arr.shape[0] != channel_count:
        mismatches.append(
            f"Coordinate channel count ({coord_arr.shape[0]}) does not match data channel count ({channel_count})"
        )

    if not np.all(np.isfinite(coord_arr)):
        mismatches.append("Coordinates contain non-finite values (NaN/Inf)")

    return mismatches


def check_finite_values(data: Any) -> list[str]:
    """Strictly verify that numerical payloads contain only finite values (no NaN or Inf)."""
    mismatches: list[str] = []
    if data is None:
        return mismatches

    arr = np.asarray(data)
    if arr.size > 0:
        if not np.all(np.isfinite(arr)):
            mismatches.append("Payload array contains non-finite values (NaN or Inf)")
    return mismatches


def check_schema_version(
    expected_schema: str | None,
    observed_schema: str | None,
) -> list[str]:
    """Verify that schema versions are recognized and compatible."""
    mismatches: list[str] = []
    if expected_schema is None or expected_schema == "":
        return mismatches
    if observed_schema is None or observed_schema == "":
        mismatches.append(f"Missing schema_version; expected '{expected_schema}'")
        return mismatches

    # Check major version / family
    if observed_schema != expected_schema:
        # Check if known stale or deprecated
        if "legacy" in observed_schema.lower() or "deprecated" in observed_schema.lower():
            mismatches.append(
                f"Stale/deprecated schema version observed: '{observed_schema}', expected '{expected_schema}'"
            )
        else:
            mismatches.append(
                f"Schema version mismatch: expected '{expected_schema}', observed '{observed_schema}'"
            )
    return mismatches


def check_optional_dependency(dependency_name: str) -> tuple[bool, str]:
    """Check availability of optional external dependencies without throwing unhandled exceptions."""
    try:
        mod = importlib.import_module(dependency_name)
        ver = getattr(mod, "__version__", "unknown")
        return True, str(ver)
    except ImportError:
        return False, "not_installed"
    except Exception as exc:
        return False, f"error_importing: {exc}"


def evaluate_boundary(
    boundary_id: str,
    producer_stage_id: str,
    consumer_stage_id: str,
    expected_contract: Mapping[str, Any],
    observed_contract: Mapping[str, Any],
    payload: Any = None,
    dependency_override: dict[str, bool] | None = None,
) -> BoundaryReport:
    """Evaluate structural conformance at an inter-stage boundary.

    Returns a detailed BoundaryReport with status:
    - COMPATIBLE: All required contracts, dimensions, units, orderings, and schemas match.
    - INCOMPATIBLE: Structural mismatch, reordered channels, unit conflict, non-finite values, or version error.
    - MISSING_REQUIRED_FIELD: Mandatory metadata (e.g. units, rate, timestamps) absent.
    - NOT_COMPARABLE: Required optional dependency unavailable.
    """
    mismatches: list[str] = []
    missing_fields: list[str] = []
    diagnostics: dict[str, Any] = {}

    # 1. Dependency check
    required_dep = expected_contract.get("required_dependency")
    if required_dep:
        if dependency_override and required_dep in dependency_override:
            dep_available = dependency_override[required_dep]
            dep_ver = "mock_available" if dep_available else "mock_unavailable"
        else:
            dep_available, dep_ver = check_optional_dependency(required_dep)

        diagnostics["dependency_name"] = required_dep
        diagnostics["dependency_version"] = dep_ver
        if not dep_available:
            return BoundaryReport(
                boundary_id=boundary_id,
                producer_stage_id=producer_stage_id,
                consumer_stage_id=consumer_stage_id,
                status=BoundaryStatus.NOT_COMPARABLE.value,
                input_artifact_ref=str(observed_contract.get("artifact_id", "observed")),
                output_artifact_ref=str(expected_contract.get("expected_artifact_id", "expected")),
                expected_contract=dict(expected_contract),
                observed_contract=dict(observed_contract),
                mismatches=[f"Required optional dependency '{required_dep}' is not available"],
                missing_fields=[],
                diagnostics=diagnostics,
            )

    # 2. Schema check
    exp_schema = expected_contract.get("schema_version")
    obs_schema = observed_contract.get("schema_version")
    mismatches.extend(check_schema_version(exp_schema, obs_schema))

    # 3. Shape check
    exp_shape = expected_contract.get("expected_shape")
    obs_shape = observed_contract.get("observed_shape")
    mismatches.extend(check_shape_conformance(exp_shape, obs_shape))

    # 4. Channel ordering check
    exp_channels = expected_contract.get("channel_ordering")
    obs_channels = observed_contract.get("channel_ordering")
    mismatches.extend(check_channel_ordering_conformance(exp_channels, obs_channels))

    # 5. Units check
    exp_units = expected_contract.get("expected_units")
    obs_units = observed_contract.get("observed_units")
    mismatches.extend(check_unit_conformance(exp_units, obs_units))

    # 6. Timing check
    exp_rate = expected_contract.get("sampling_rate_hz")
    obs_rate = observed_contract.get("sampling_rate_hz")
    sample_cnt = observed_contract.get("sample_count")
    timestamps = observed_contract.get("timestamps")
    require_ts = bool(expected_contract.get("require_timestamps", False))
    timing_mismatches, timing_missing = check_timing_conformance(
        exp_rate, obs_rate, sample_count=sample_cnt, timestamps=timestamps, require_timestamps=require_ts
    )
    mismatches.extend(timing_mismatches)
    missing_fields.extend(timing_missing)

    # 7. Coordinates check
    coords = observed_contract.get("montage_coordinates")
    coord_status = observed_contract.get("coordinate_status")
    ch_cnt = len(obs_channels) if obs_channels else None
    mismatches.extend(check_coordinate_conformance(coords, ch_cnt, coord_status))

    # 8. Finite value check on payload
    if payload is not None:
        mismatches.extend(check_finite_values(payload))

    # 9. Incompatible stage check (e.g. wrong artifact kind / feature family)
    exp_kind = expected_contract.get("expected_artifact_type")
    obs_kind = observed_contract.get("artifact_type")
    if exp_kind and obs_kind and exp_kind != obs_kind:
        mismatches.append(
            f"Incompatible stage artifact type: expected '{exp_kind}', observed '{obs_kind}'"
        )

    exp_family = expected_contract.get("expected_feature_family")
    obs_family = observed_contract.get("feature_family")
    if exp_family and obs_family and exp_family != obs_family:
        mismatches.append(
            f"Incompatible feature family: expected '{exp_family}', observed '{obs_family}'"
        )

    # Outcome resolution
    if missing_fields:
        status = BoundaryStatus.MISSING_REQUIRED_FIELD.value
    elif mismatches:
        status = BoundaryStatus.INCOMPATIBLE.value
    else:
        status = BoundaryStatus.COMPATIBLE.value

    def _sanitize_contract(c: Mapping[str, Any]) -> dict[str, Any]:
        sanitized = {}
        for k, v in c.items():
            if k in ("data", "timestamps", "pairwise_fc_matrix", "signal_chunk", "feature_bundle", "psd_record", "fc_record"):
                if hasattr(v, "shape"):
                    sanitized[f"{k}_shape"] = list(v.shape)
                elif isinstance(v, (list, tuple)):
                    sanitized[f"{k}_len"] = len(v)
                continue
            sanitized[k] = v
        return sanitized

    return BoundaryReport(
        boundary_id=boundary_id,
        producer_stage_id=producer_stage_id,
        consumer_stage_id=consumer_stage_id,
        status=status,
        input_artifact_ref=str(observed_contract.get("artifact_id", "observed")),
        output_artifact_ref=str(expected_contract.get("expected_artifact_id", "expected")),
        expected_contract=_sanitize_contract(expected_contract),
        observed_contract=_sanitize_contract(observed_contract),
        mismatches=mismatches,
        missing_fields=missing_fields,
        diagnostics=diagnostics,
    )
