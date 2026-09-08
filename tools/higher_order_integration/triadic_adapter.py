"""Adapter from bounded triadic-connectivity results to canonical feature records.

The adapter deliberately has no scientific solver and no network behavior.  It
normalizes an explicit input envelope, rejects ambiguous provenance, and emits
one deterministic, null-safe feature record.  It does not create a
``RunRecordV1`` replacement; callers may reference the record from a canonical
run record's metrics or artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any


INPUT_SCHEMA_VERSION = "triadic-functional-connectivity-input-v1"
FEATURE_SCHEMA_VERSION = "triadic-feature-contract-v1"
ADAPTER_VERSION = "triadic-feature-contract-adapter-v1"

_CHECKSUM_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_ESTIMATORS = frozenset(
    {
        "matrix_entropy_covariance",
        "residualized_three_variable_dependence",
        "combined_matrix_entropy_residualized",
    }
)
_SURROGATES = frozenset(
    {
        "none",
        "amplitude_shuffle",
        "phase_shuffle",
        "circular_shift",
        "block_shift",
    }
)
_TOPOLOGY_KEYS = frozenset(
    {
        "beta1",
        "graph_beta1",
        "graph_beta_1",
        "spatial_winding",
        "spatial_charge",
        "spatial_phase_charge",
        "topological_charge",
        "scalar_chirality",
        "causal_influence",
        "directed_causal_influence",
    }
)
_BEHAVIOR_KEYS = frozenset(
    {
        "behavior",
        "behavior_label",
        "inferred_behavior",
        "subject_state",
        "phenotype",
        "consciousness",
        "mechanism",
        "causal_label",
    }
)


class TriadicContractError(ValueError):
    """Raised when an input cannot satisfy the triadic feature contract."""


def _plain(value: Any) -> Any:
    """Convert JSON-like values, including NumPy scalars, to Python values."""

    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (str, bool, int)) or value is None:
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [_plain(item) for item in value]
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _plain(item())
        except (TypeError, ValueError):
            pass
    raise TriadicContractError(f"unsupported non-JSON value: {type(value).__name__}")


def _json_safe(value: Any) -> Any:
    """Return JSON-safe data, using null for unavailable/non-finite metrics."""

    value = _plain(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def canonical_json(value: Any) -> str:
    """Serialize JSON deterministically and reject accidental non-JSON values."""

    return json.dumps(
        _json_safe(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TriadicContractError(f"{name} must be an object")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TriadicContractError(f"{name} must be a non-empty string")
    return value.strip()


def _finite(value: Any, name: str, *, nonnegative: bool = False) -> float:
    if isinstance(value, bool):
        raise TriadicContractError(f"{name} must be finite numeric data")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise TriadicContractError(f"{name} must be finite numeric data") from None
    if not math.isfinite(number) or (nonnegative and number < 0):
        raise TriadicContractError(f"{name} must be finite numeric data")
    return number


def _integer(value: Any, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise TriadicContractError(f"{name} must be an integer >= {minimum}")
    return value


def _checksum(value: Any, name: str) -> str:
    value = _text(value, name).lower()
    if not _CHECKSUM_RE.fullmatch(value):
        raise TriadicContractError(f"{name} must be a 64-character SHA-256 hex digest")
    return value


def _walk_for_forbidden_keys(value: Any, forbidden: frozenset[str], *, context: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in forbidden:
                raise TriadicContractError(f"{context} contains forbidden field {key!r}")
            _walk_for_forbidden_keys(item, forbidden, context=context)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _walk_for_forbidden_keys(item, forbidden, context=context)


def _validate_no_topology_labels(interactions: Sequence[Any], top_triads: Sequence[Any]) -> None:
    _walk_for_forbidden_keys(interactions, _TOPOLOGY_KEYS, context="triadic interactions")
    _walk_for_forbidden_keys(top_triads, _TOPOLOGY_KEYS, context="top triads")


def _triad_indices(item: Mapping[str, Any], channel_count: int) -> tuple[int, int, int]:
    raw = item.get("channel_indices", item.get("channels"))
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)) or len(raw) != 3:
        raise TriadicContractError("each triad must contain exactly three channel indices")
    if any(isinstance(index, bool) or not isinstance(index, int) for index in raw):
        raise TriadicContractError("triad channel indices must be integers")
    indices = tuple(raw)
    if len(set(indices)) != 3 or any(index < 0 or index >= channel_count for index in indices):
        raise TriadicContractError("triad channel indices must be three distinct valid channels")
    return indices  # type: ignore[return-value]


def _indices_from_triad_id(triad_id: str, channel_count: int) -> tuple[int, int, int]:
    match = re.fullmatch(r"triad:(\d+),(\d+),(\d+)", triad_id)
    if match is None:
        raise TriadicContractError(f"invalid triad ID {triad_id!r}")
    return _triad_indices({"channel_indices": [int(value) for value in match.groups()]}, channel_count)


def _score(item: Mapping[str, Any], name: str) -> float | None:
    value = item.get(name)
    if value is None:
        return None
    return _finite(value, f"triad {name}")


def _sort_key(item: Mapping[str, Any]) -> tuple[float, str]:
    score = item.get("combined_score")
    return (-(float(score) if score is not None else float("-inf")), str(item["triad_id"]))


def _control(value: Any, name: str) -> Any:
    if value is None:
        return None
    return _json_safe(_mapping(value, name))


@dataclass(frozen=True)
class CanonicalTriadicFeatureRecord:
    """Immutable serialized feature record produced by the adapter."""

    payload: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(dict(self.payload))

    def to_json(self) -> str:
        return canonical_json(self.payload)

    def to_markdown(self) -> str:
        data = self.to_dict()
        provenance = data["provenance"]
        telemetry = data["complexity_telemetry"]
        findings = data["validation_findings"]
        lines = [
            "# Triadic Feature Contract",
            "",
            f"- Schema version: `{data['schema_version']}`",
            f"- Input schema: `{data['input_schema_version']}`",
            f"- Evidence class: `{data['evidence_class']}`",
            f"- Synthetic demo: `{data['synthetic_demo']}`",
            f"- Source checksum: `{provenance['source_checksum']}`",
            f"- Adapter checksum: `{data['adapter_checksum']}`",
            "",
            "## Validation",
            "",
            f"- Status: `{findings['status']}`",
            f"- Errors: {len(findings['errors'])}",
            f"- Warnings: {len(findings['warnings'])}",
            "",
            "## Normalized analysis",
            "",
            f"- Estimator: `{data['method']['estimator']}`",
            f"- Surrogate: `{data['method']['surrogate_method']}`",
            f"- Seed: `{data['method']['seed']}`",
            f"- Channels: {len(data['channels'])}",
            f"- Triads: {len(data['features']['triadic_statistical_dependence']['triads'])}",
            f"- Candidate count: {telemetry['candidate_count']}",
            f"- Maximum triads: {telemetry['max_triads']}",
            f"- Candidate memory bytes: {telemetry['estimated_candidate_memory_bytes']}",
            "",
            "## Feature namespaces",
            "",
            "The triadic score is a statistical dependence feature only. Pairwise, PSD, common-driver, graph beta-1, spatial charge, and causal influence remain separate namespaces.",
            "",
            "```json",
            canonical_json(data["features"]),
            "```",
        ]
        return "\n".join(lines) + "\n"


def adapt_triadic_output(envelope: Mapping[str, Any]) -> CanonicalTriadicFeatureRecord:
    """Validate and adapt one explicit triadic input envelope.

    The envelope is intentionally stricter than a solver's internal result:
    units, sampling, condition labels, bounded resource telemetry, estimator,
    and provenance must be declared by the producer and are never inferred.
    """

    envelope = _mapping(envelope, "input envelope")
    if envelope.get("schema_version") != INPUT_SCHEMA_VERSION:
        raise TriadicContractError(f"schema_version must be {INPUT_SCHEMA_VERSION!r}")
    _walk_for_forbidden_keys(envelope, _BEHAVIOR_KEYS, context="input envelope")

    channels_raw = envelope.get("channels")
    if not isinstance(channels_raw, Sequence) or isinstance(channels_raw, (str, bytes, bytearray)):
        raise TriadicContractError("channels must be an array of names")
    channels = tuple(_text(name, "channel name") for name in channels_raw)
    if len(set(channels)) != len(channels):
        raise TriadicContractError("channel names must be unique")
    if not channels:
        raise TriadicContractError("at least one channel is required")

    window = _mapping(envelope.get("window"), "window")
    window_id = _text(window.get("window_id"), "window.window_id")
    start_s = _finite(window.get("start_s"), "window.start_s")
    end_s = _finite(window.get("end_s"), "window.end_s")
    if end_s < start_s:
        raise TriadicContractError("window.end_s must be >= window.start_s")
    sample_count = _integer(window.get("sample_count"), "window.sample_count", minimum=1)
    sampling_rate_hz = _finite(window.get("sampling_rate_hz"), "window.sampling_rate_hz")
    if sampling_rate_hz <= 0:
        raise TriadicContractError("window.sampling_rate_hz must be > 0")
    units = _text(window.get("units"), "window.units")
    condition_labels_raw = window.get("condition_labels")
    if not isinstance(condition_labels_raw, Sequence) or isinstance(condition_labels_raw, (str, bytes, bytearray)):
        raise TriadicContractError("window.condition_labels must be explicitly declared as an array")
    condition_labels = tuple(_text(label, "condition label") for label in condition_labels_raw)
    if not condition_labels:
        raise TriadicContractError("at least one explicit condition label is required")
    if len(set(condition_labels)) != len(condition_labels):
        raise TriadicContractError("condition labels must be unique")

    method = _mapping(envelope.get("method"), "method")
    estimator = _text(method.get("estimator"), "method.estimator")
    if estimator not in _ESTIMATORS:
        raise TriadicContractError(f"unsupported or undeclared estimator: {estimator!r}")
    surrogate_method = _text(method.get("surrogate_method"), "method.surrogate_method")
    if surrogate_method not in _SURROGATES:
        raise TriadicContractError(f"unsupported surrogate method: {surrogate_method!r}")
    seed = method.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise TriadicContractError("method.seed must be a deterministic non-negative integer")

    resources = _mapping(envelope.get("resources"), "resources")
    candidate_count = _integer(
        resources.get("candidate_count", resources.get("candidate_triads")),
        "resources.candidate_count",
        minimum=0,
    )
    max_triads = _integer(resources.get("max_triads"), "resources.max_triads", minimum=1)
    if candidate_count > max_triads:
        raise TriadicContractError("candidate_count cannot exceed max_triads")
    if resources.get("bounded") is not True:
        raise TriadicContractError("resources.bounded must be true")
    memory = _mapping(resources.get("memory_telemetry"), "resources.memory_telemetry")
    memory_telemetry = {
        "estimated_input_memory_bytes": _finite(memory.get("estimated_input_memory_bytes"), "memory input bytes", nonnegative=True),
        "estimated_candidate_memory_bytes": _finite(memory.get("estimated_candidate_memory_bytes"), "memory candidate bytes", nonnegative=True),
    }

    provenance = _mapping(envelope.get("provenance"), "provenance")
    source_id = _text(provenance.get("source_id"), "provenance.source_id")
    source_checksum = _checksum(provenance.get("source_checksum"), "provenance.source_checksum")
    declared_provenance_checksum = _checksum(provenance.get("provenance_checksum"), "provenance.provenance_checksum")
    data_mode = _text(provenance.get("data_mode"), "provenance.data_mode")
    synthetic_demo = provenance.get("synthetic_demo")
    if not isinstance(synthetic_demo, bool):
        raise TriadicContractError("provenance.synthetic_demo must be boolean")
    evidence_class = _text(provenance.get("evidence_class"), "provenance.evidence_class")
    if synthetic_demo:
        if data_mode != "synthetic_demo" or evidence_class != "synthetic_demo":
            raise TriadicContractError("synthetic data cannot be marked empirical")
    else:
        if data_mode != "empirical" or evidence_class not in {"empirical", "empirical_provenance_complete"}:
            raise TriadicContractError("empirical status must be explicit and provenance-complete")

    result = _mapping(envelope.get("result"), "result")
    interactions_raw = result.get("interactions")
    if not isinstance(interactions_raw, Sequence) or isinstance(interactions_raw, (str, bytes, bytearray)):
        raise TriadicContractError("result.interactions must be an array")
    top_triads_raw = result.get("top_triads", [])
    if not isinstance(top_triads_raw, Sequence) or isinstance(top_triads_raw, (str, bytes, bytearray)):
        raise TriadicContractError("result.top_triads must be an array")
    _validate_no_topology_labels(interactions_raw, top_triads_raw)

    normalized_interactions: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw_item in interactions_raw:
        item = _mapping(raw_item, "triadic interaction")
        indices = _triad_indices(item, len(channels))
        canonical_indices = tuple(sorted(indices))
        expected_id = "triad:" + ",".join(str(index) for index in canonical_indices)
        triad_id = item.get("triad_id", expected_id)
        triad_id = _text(triad_id, "triad_id")
        if triad_id != expected_id:
            raise TriadicContractError(f"invalid triad ID {triad_id!r}; expected {expected_id!r}")
        if triad_id in seen_ids:
            raise TriadicContractError(f"duplicate triad ID: {triad_id}")
        seen_ids.add(triad_id)
        condition = item.get("condition_label")
        if condition is not None and _text(condition, "condition_label") not in condition_labels:
            raise TriadicContractError("interaction condition_label is not declared by the window")
        declared_labels = item.get("channel_labels")
        if declared_labels is not None:
            if not isinstance(declared_labels, Sequence) or isinstance(declared_labels, (str, bytes, bytearray)) or len(declared_labels) != 3:
                raise TriadicContractError("channel_labels must contain three names when supplied")
            if tuple(_text(label, "channel label") for label in declared_labels) != tuple(channels[index] for index in canonical_indices):
                raise TriadicContractError("channel_labels do not match channel_indices")
        normalized_interactions.append(
            {
                "triad_id": triad_id,
                "channel_indices": list(canonical_indices),
                "channel_names": [channels[index] for index in canonical_indices],
                "matrix_entropy_score": _score(item, "matrix_entropy_score"),
                "nonlinear_interaction_score": _score(item, "nonlinear_interaction_score"),
                "combined_score": _score(item, "combined_score"),
                "sample_count": _integer(item.get("sample_count", sample_count), "triad sample_count", minimum=1),
                "condition_label": condition,
            }
        )
    normalized_interactions.sort(key=_sort_key)
    for item in normalized_interactions:
        if item["sample_count"] != sample_count:
            raise TriadicContractError("triad sample_count must match window.sample_count")
    if len(normalized_interactions) > candidate_count:
        raise TriadicContractError("candidate_count cannot be smaller than the declared interaction count")

    top_ids: list[str] = []
    for raw_item in top_triads_raw:
        item = _mapping(raw_item, "top triad")
        if "channel_indices" in item or "channels" in item:
            raw_indices = _triad_indices(item, len(channels))
        else:
            declared_top_id = _text(item.get("triad_id"), "top triad ID")
            raw_indices = _indices_from_triad_id(declared_top_id, len(channels))
        expected_id = "triad:" + ",".join(str(index) for index in sorted(raw_indices))
        triad_id = _text(item.get("triad_id", expected_id), "top triad ID")
        if triad_id != expected_id:
            raise TriadicContractError(f"invalid top triad ID {triad_id!r}; expected {expected_id!r}")
        if triad_id not in seen_ids:
            raise TriadicContractError("top triads must refer to declared interactions")
        if triad_id in top_ids:
            raise TriadicContractError(f"duplicate top triad ID: {triad_id}")
        top_ids.append(triad_id)
    sorted_top_ids = [item["triad_id"] for item in normalized_interactions if item["triad_id"] in top_ids]
    top_ids = sorted_top_ids

    complexity = _mapping(result.get("complexity_telemetry"), "result.complexity_telemetry")
    input_channels = _integer(complexity.get("input_channels"), "complexity input_channels", minimum=1)
    if input_channels != len(channels):
        raise TriadicContractError("complexity input_channels must match channel count")
    result_candidate_count = _integer(
        complexity.get("candidate_count", complexity.get("candidate_triads", candidate_count)),
        "result candidate_count",
        minimum=0,
    )
    if result_candidate_count != candidate_count:
        raise TriadicContractError("candidate count differs between resource and result telemetry")

    controls = _mapping(result.get("controls", {}), "result.controls")
    pairwise_control = controls.get("pairwise_connectivity", result.get("pairwise_control"))
    psd_control = controls.get("psd_control", result.get("psd_control"))
    common_driver_control = controls.get("common_driver_control", result.get("common_driver_control"))
    for key in controls:
        normalized_key = str(key).lower().replace("-", "_")
        if normalized_key in _TOPOLOGY_KEYS:
            raise TriadicContractError("topology labels cannot be attached to triadic statistical scores")
    canonical_provenance = {
        "source_id": source_id,
        "source_checksum": source_checksum,
        "provenance_checksum": declared_provenance_checksum,
        "data_mode": data_mode,
        "synthetic_demo": synthetic_demo,
        "evidence_class": "synthetic_demo" if synthetic_demo else "empirical_provenance_complete",
    }
    triadic_features = {
        "estimator": estimator,
        "triads": normalized_interactions,
        "top_triads": top_ids,
        "finite_value_status": "FINITE",
        "statistical_interpretation": "triadic_statistical_dependence_only",
    }
    features = {
        "triadic_statistical_dependence": triadic_features,
        "pairwise_connectivity": _control(pairwise_control, "pairwise_connectivity"),
        "psd_control": _control(psd_control, "psd_control"),
        "common_driver_control": _control(common_driver_control, "common_driver_control"),
        "graph_beta_1": {"status": "separate_namespace", "value": None},
        "spatial_phase_charge": {"status": "separate_namespace", "value": None},
        "causal_influence": {"status": "separate_namespace", "value": None},
    }
    payload: dict[str, Any] = {
        "schema_version": FEATURE_SCHEMA_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "input_schema_version": INPUT_SCHEMA_VERSION,
        "evidence_class": canonical_provenance["evidence_class"],
        "synthetic_demo": synthetic_demo,
        "channels": list(channels),
        "time_window": {
            "window_id": window_id,
            "start_s": start_s,
            "end_s": end_s,
            "sample_count": sample_count,
            "sampling_rate_hz": sampling_rate_hz,
            "units": units,
            "condition_labels": list(condition_labels),
        },
        "method": {"estimator": estimator, "surrogate_method": surrogate_method, "seed": seed},
        "complexity_telemetry": {
            "candidate_count": candidate_count,
            "max_triads": max_triads,
            "bounded": True,
            **memory_telemetry,
        },
        "provenance": canonical_provenance,
        "features": features,
        "validation_findings": {
            "status": "VALID",
            "errors": [],
            "warnings": list(result.get("warnings", [])) if isinstance(result.get("warnings", []), list) else [],
            "no_inferred_behavioral_labels": True,
            "topology_separation": "enforced",
        },
    }
    payload["adapter_checksum"] = sha256_json(payload)
    return CanonicalTriadicFeatureRecord(payload=payload)


def validate_serialized_feature_record(record: Mapping[str, Any]) -> None:
    """Validate finite JSON and the deterministic adapter checksum."""

    data = _mapping(record, "feature record")
    if data.get("schema_version") != FEATURE_SCHEMA_VERSION:
        raise TriadicContractError("invalid feature record schema version")
    expected = data.get("adapter_checksum")
    if not isinstance(expected, str):
        raise TriadicContractError("feature record is missing adapter_checksum")
    without_checksum = dict(data)
    without_checksum.pop("adapter_checksum", None)
    if expected != sha256_json(without_checksum):
        raise TriadicContractError("adapter checksum does not match canonical payload")
    serialized = canonical_json(data)
    if any(token in serialized for token in ("NaN", "Infinity", "-Infinity")):
        raise TriadicContractError("feature record contains non-finite JSON")
