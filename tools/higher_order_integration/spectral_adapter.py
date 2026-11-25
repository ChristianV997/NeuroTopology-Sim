"""Adapter from higher-order spectral reports to canonical frequency records.

The adapter is intentionally independent of the estimator implementation. It
accepts JSON-compatible mappings, validates their axes and metadata, and emits
comparison-ready descriptive records. It never converts spectral structure
into topology, causality, or mental-state evidence.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from numbers import Real
from typing import Any, Iterable, Mapping, Optional

SCHEMA_VERSION = "NeuroTopologySim.SpectralFeatureContract.v1"
FEATURE_FAMILIES = (
    "psd",
    "cross_spectrum",
    "pac",
    "bispectrum",
    "trispectrum_slice",
    "modulogram",
    "pairwise_cross_frequency",
)
EVIDENCE_CLASSES = (
    "empirical_signal_processing_descriptive",
    "synthetic_signal_processing_descriptive",
    "unknown_signal_mode",
)


def _number(value: Any, path: str, errors: list[str], *, allow_none: bool = True) -> Optional[float]:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, Real):
        errors.append(f"{path}: expected a finite numeric value or null")
        return None
    result = float(value)
    if not math.isfinite(result):
        errors.append(f"{path}: nonfinite value")
        return None
    return result


def _json_value(value: Any, path: str, errors: list[str]) -> Any:
    """Normalize nested numeric values, including explicit complex pairs."""
    if value is None:
        return None
    if isinstance(value, complex):
        real = _number(value.real, path + ".real", errors, allow_none=False)
        imag = _number(value.imag, path + ".imag", errors, allow_none=False)
        return {"real": real, "imag": imag}
    if isinstance(value, Mapping):
        if set(value) == {"real", "imag"}:
            real = _number(value.get("real"), path + ".real", errors)
            imag = _number(value.get("imag"), path + ".imag", errors)
            return {"real": real, "imag": imag}
        return {str(key): _json_value(item, f"{path}.{key}", errors) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item, f"{path}[{index}]", errors) for index, item in enumerate(value)]
    if isinstance(value, Real) and not isinstance(value, bool):
        return _number(value, path, errors, allow_none=False)
    errors.append(f"{path}: unsupported value type {type(value).__name__}")
    return None


def _shape(value: Any) -> tuple[int, ...]:
    if not isinstance(value, list):
        return ()
    if not value:
        return (0,)
    child = _shape(value[0])
    if any(_shape(item) != child for item in value):
        return (-1,)
    return (len(value),) + child


def _validate_finite_tree(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, Mapping):
        if set(value) == {"real", "imag"}:
            _number(value.get("real"), path + ".real", errors)
            _number(value.get("imag"), path + ".imag", errors)
        else:
            for key, item in value.items():
                _validate_finite_tree(item, f"{path}.{key}", errors)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_finite_tree(item, f"{path}[{index}]", errors)


def _axis(
    node: Mapping[str, Any] | None,
    path: str,
    errors: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    if not isinstance(node, Mapping):
        errors.append(f"{path}: missing frequency axis")
        return {"frequencies_hz": [], "units": "Hz", "resolution_hz": None, "nyquist_hz": None}
    raw = node.get("frequencies_hz")
    if not isinstance(raw, list) or not raw:
        errors.append(f"{path}.frequencies_hz: non-empty list required")
        frequencies: list[Optional[float]] = []
    else:
        frequencies = [_number(item, f"{path}.frequencies_hz[{index}]", errors, allow_none=False) for index, item in enumerate(raw)]
        numeric = [item for item in frequencies if item is not None]
        if any(right <= left for left, right in zip(numeric, numeric[1:])):
            errors.append(f"{path}.frequencies_hz: axis must be strictly monotonic")
    units = node.get("units", "Hz")
    if not isinstance(units, str) or not units:
        errors.append(f"{path}.units: non-empty string required")
        units = "Hz"
    resolution = _number(node.get("resolution_hz"), f"{path}.resolution_hz", errors)
    if resolution is not None and resolution <= 0.0:
        errors.append(f"{path}.resolution_hz: must be positive")
    nyquist = _number(node.get("nyquist_hz"), f"{path}.nyquist_hz", errors)
    if "resolution_hz" not in node:
        warnings.append(f"{path}: frequency resolution was not declared")
    return {
        "frequencies_hz": frequencies,
        "resolution_hz": resolution,
        "nyquist_hz": nyquist,
        "units": units,
    }


def _metadata(report: Mapping[str, Any], channel_identity: Any, condition_label: Any) -> dict[str, Any]:
    provenance = report.get("provenance") if isinstance(report.get("provenance"), Mapping) else {}
    config = report.get("segment_configuration") if isinstance(report.get("segment_configuration"), Mapping) else {}
    synthetic = provenance.get("synthetic")
    evidence = (
        "synthetic_signal_processing_descriptive" if synthetic is True
        else "empirical_signal_processing_descriptive" if synthetic is False
        else "unknown_signal_mode"
    )
    controls = report.get("surrogates") if isinstance(report.get("surrogates"), list) else []
    return {
        "schema_version": SCHEMA_VERSION,
        "input_schema_version": report.get("schema_version"),
        "sampling_rate_hz": provenance.get("sampling_rate_hz"),
        "frequency_units": "Hz",
        "fft_length": config.get("n_fft"),
        "segment_length": config.get("segment_length"),
        "overlap": config.get("overlap"),
        "taper": config.get("taper"),
        "frequency_resolution_hz": None,
        "channel_identity": channel_identity if channel_identity is not None else report.get("channel_identity"),
        "condition_label": condition_label if condition_label is not None else report.get("condition_label"),
        "memory_budget_bytes": config.get("memory_budget_bytes"),
        "source_checksum_sha256": provenance.get("checksum_sha256"),
        "synthetic": synthetic,
        "evidence_class": evidence,
        "surrogate_controls": controls,
        "normalization": config.get("normalization"),
    }


@dataclass(frozen=True)
class CanonicalFrequencyRecord:
    feature_family: str
    feature_name: str
    values: Any
    frequency_axes: dict[str, Any]
    value_shape: tuple[int, ...]
    metadata: dict[str, Any]
    filtering_status: str
    edge_effects: Any
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["value_shape"] = list(self.value_shape)
        result["warnings"] = list(self.warnings)
        result["errors"] = list(self.errors)
        return result


@dataclass(frozen=True)
class SpectralFeatureContract:
    schema_version: str
    evidence_class: str
    synthetic: Optional[bool]
    source_checksum_sha256: Optional[str]
    records: tuple[CanonicalFrequencyRecord, ...]
    validation_errors: tuple[str, ...] = ()
    validation_warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_class": self.evidence_class,
            "synthetic": self.synthetic,
            "source_checksum_sha256": self.source_checksum_sha256,
            "records": [record.to_dict() for record in self.records],
            "validation_errors": list(self.validation_errors),
            "validation_warnings": list(self.validation_warnings),
        }


def _filter_and_edges(report: Mapping[str, Any], warnings: list[str]) -> tuple[str, Any]:
    preprocessing = report.get("preprocessing") if isinstance(report.get("preprocessing"), Mapping) else {}
    filtering = preprocessing.get("filtering", report.get("filtering"))
    if filtering is None:
        warnings.append("filtering metadata is absent; no claim of unfiltered data is made")
        filtering_status = "not_declared"
    elif filtering in (False, "none", "None", "no_filter"):
        filtering_status = "none_declared"
    else:
        filtering_status = "declared"
    diagnostics = report.get("diagnostics") if isinstance(report.get("diagnostics"), Mapping) else {}
    edge = diagnostics.get("edge_effect_warning", diagnostics.get("edge_effects"))
    if edge is None:
        warnings.append("edge-effect metadata is absent")
        edge = {"declared": False, "warning": None}
    else:
        edge = {"declared": True, "warning": edge}
    return filtering_status, edge


def _record(
    report: Mapping[str, Any],
    family: str,
    feature_name: str,
    values: Any,
    axes: dict[str, Any],
    *,
    channel_identity: Any,
    condition_label: Any,
    errors: list[str],
    warnings: list[str],
    nonnegative: bool = False,
    expected_shape: tuple[int, ...] | None = None,
    shape_override: tuple[int, ...] | None = None,
    metadata_extra: Mapping[str, Any] | None = None,
) -> CanonicalFrequencyRecord:
    if family not in FEATURE_FAMILIES:
        errors.append(f"{family}: unsupported feature family")
    normalized = _json_value(values, f"{family}.values", errors)
    _validate_finite_tree(normalized, f"{family}.values", errors)
    shape = shape_override or _shape(normalized)
    if expected_shape is not None and shape != expected_shape:
        errors.append(f"{family}.values: shape {shape} is incompatible with expected {expected_shape}")
    if nonnegative:
        def visit(value: Any, path: str) -> None:
            if isinstance(value, Mapping):
                if set(value) == {"real", "imag"}:
                    return
                for key, item in value.items():
                    visit(item, f"{path}.{key}")
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    visit(item, f"{path}[{index}]")
            elif value is not None and value < 0.0:
                errors.append(f"{path}: PSD-like values must be nonnegative")
        visit(normalized, f"{family}.values")
    metadata = _metadata(report, channel_identity, condition_label)
    if axes:
        first_axis = next(iter(axes.values()))
        metadata["frequency_resolution_hz"] = first_axis.get("resolution_hz")
        metadata["frequency_units"] = first_axis.get("units", "Hz")
    if metadata_extra:
        metadata.update(metadata_extra)
    filtering_status, edge = _filter_and_edges(report, warnings)
    return CanonicalFrequencyRecord(
        feature_family=family,
        feature_name=feature_name,
        values=normalized,
        frequency_axes=axes,
        value_shape=shape,
        metadata=metadata,
        filtering_status=filtering_status,
        edge_effects=edge,
        warnings=(),
        errors=(),
    )


def _record_axes(node: Mapping[str, Any], path: str, errors: list[str], warnings: list[str]) -> dict[str, Any]:
    axis = _axis(node.get("frequency_axis"), path + ".frequency_axis", errors, warnings)
    return {"frequency": axis}


def _surrogate_controls(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = report.get("surrogates")
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, Mapping)]


def validate_spectral_feature_report(report: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    """Validate report-level metadata without mutating the input."""
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(report, Mapping):
        return ["report must be a mapping"], []
    provenance = report.get("provenance")
    if not isinstance(provenance, Mapping):
        errors.append("provenance: required mapping is missing")
    else:
        rate = _number(provenance.get("sampling_rate_hz"), "provenance.sampling_rate_hz", errors)
        if rate is None or rate <= 0.0:
            errors.append("provenance.sampling_rate_hz: must be positive")
        synthetic = provenance.get("synthetic")
        if not isinstance(synthetic, bool):
            errors.append("provenance.synthetic: explicit boolean required")
        checksum = provenance.get("checksum_sha256")
        if not isinstance(checksum, str) or len(checksum) != 64:
            errors.append("provenance.checksum_sha256: 64-character checksum required")
    config = report.get("segment_configuration")
    if not isinstance(config, Mapping):
        errors.append("segment_configuration: required mapping is missing")
    else:
        for key in ("n_fft", "segment_length", "overlap", "taper", "frequency_bins", "memory_budget_bytes"):
            if key not in config:
                errors.append(f"segment_configuration.{key}: required metadata is missing")
    _filter_and_edges(report, warnings)
    return errors, warnings


def adapt_spectral_feature_report(
    report: Mapping[str, Any],
    *,
    channel_identity: Any = None,
    condition_label: Any = None,
) -> SpectralFeatureContract:
    """Normalize all available comparison and higher-order feature families."""
    errors, warnings = validate_spectral_feature_report(report)
    if not isinstance(report, Mapping):
        return SpectralFeatureContract(SCHEMA_VERSION, "unknown_signal_mode", None, None, (), tuple(errors), tuple(warnings))
    provenance = report.get("provenance") if isinstance(report.get("provenance"), Mapping) else {}
    synthetic = provenance.get("synthetic") if isinstance(provenance.get("synthetic"), bool) else None
    evidence = "synthetic_signal_processing_descriptive" if synthetic is True else "empirical_signal_processing_descriptive" if synthetic is False else "unknown_signal_mode"
    checksum = provenance.get("checksum_sha256") if isinstance(provenance.get("checksum_sha256"), str) else None
    records: list[CanonicalFrequencyRecord] = []

    def add(family: str, name: str, node: Any, values: Any, axes: dict[str, Any], **kwargs: Any) -> None:
        if isinstance(node, Mapping):
            records.append(_record(report, family, name, values, axes, channel_identity=channel_identity, condition_label=condition_label, errors=errors, warnings=warnings, **kwargs))

    bispectrum = report.get("bispectrum")
    if isinstance(bispectrum, Mapping):
        axes = _record_axes(bispectrum, "bispectrum", errors, warnings)
        axis_len = len(axes["frequency"]["frequencies_hz"])
        magnitude_shape = _shape(bispectrum.get("magnitude"))
        bicoherence_shape = _shape(bispectrum.get("bicoherence"))
        if magnitude_shape != (axis_len, axis_len) or bicoherence_shape != (axis_len, axis_len):
            errors.append("bispectrum: magnitude and bicoherence shapes must match the frequency axis")
        add("bispectrum", "bispectrum_magnitude", bispectrum, {"magnitude": bispectrum.get("magnitude"), "bicoherence": bispectrum.get("bicoherence")}, axes, nonnegative=True, shape_override=(2, axis_len, axis_len), metadata_extra={"segment_count": bispectrum.get("segment_count"), "normalization": bispectrum.get("normalization")})
    trispectrum = report.get("trispectrum")
    if isinstance(trispectrum, Mapping):
        axes = _record_axes(trispectrum, "trispectrum", errors, warnings)
        axis_len = len(axes["frequency"]["frequencies_hz"])
        slices = trispectrum.get("slice_frequencies_hz", [])
        slice_axes = dict(axes)
        slice_axes["slice_frequency"] = {"frequencies_hz": slices, "units": "Hz", "resolution_hz": None, "nyquist_hz": None}
        add("trispectrum_slice", "trispectrum_slice_magnitude", trispectrum, trispectrum.get("magnitude"), slice_axes, nonnegative=True, expected_shape=(len(slices), axis_len, axis_len), metadata_extra={"segment_count": trispectrum.get("segment_count"), "normalization": trispectrum.get("normalization")})
    modulogram = report.get("modulogram")
    if isinstance(modulogram, Mapping):
        carrier = _axis(modulogram.get("carrier_axis"), "modulogram.carrier_axis", errors, warnings)
        modulation = _axis(modulogram.get("modulation_axis"), "modulogram.modulation_axis", errors, warnings)
        add("modulogram", "modulogram_magnitude", modulogram, modulogram.get("magnitude"), {"carrier": carrier, "modulation": modulation}, nonnegative=True, expected_shape=(len(carrier["frequencies_hz"]), len(modulation["frequencies_hz"])), metadata_extra={"segment_count": modulogram.get("segment_count"), "normalization": modulogram.get("normalization")})

    comparisons = report.get("comparisons") if isinstance(report.get("comparisons"), Mapping) else {}
    psd = comparisons.get("psd")
    if isinstance(psd, Mapping):
        axes = _record_axes(psd, "comparisons.psd", errors, warnings)
        add("psd", "power_spectral_density", psd, psd.get("power"), axes, nonnegative=True, expected_shape=(len(axes["frequency"]["frequencies_hz"]),), metadata_extra={"segment_count": psd.get("segment_count")})
    cross = comparisons.get("cross_spectrum")
    if isinstance(cross, Mapping) and cross.get("available", True):
        axes = _record_axes(cross, "comparisons.cross_spectrum", errors, warnings)
        values = {"magnitude": cross.get("magnitude"), "phase_radians": cross.get("phase_radians")}
        axis_len = len(axes["frequency"]["frequencies_hz"])
        if _shape(values["magnitude"]) != (axis_len,) or _shape(values["phase_radians"]) != (axis_len,):
            errors.append("cross_spectrum: magnitude and phase shapes must match the frequency axis")
        add("cross_spectrum", "cross_spectrum_polar", cross, values, axes, shape_override=(2, axis_len), metadata_extra={"segment_count": cross.get("segment_count")})
    pac = comparisons.get("phase_amplitude_coupling")
    if isinstance(pac, Mapping) and pac.get("available", True):
        add("pac", "phase_amplitude_coupling", pac, {"modulation_index": pac.get("modulation_index")}, {}, nonnegative=True, shape_override=(1,), metadata_extra={"phase_band_hz": pac.get("phase_band_hz"), "amplitude_band_hz": pac.get("amplitude_band_hz"), "method": pac.get("method")})
    pairwise = comparisons.get("pairwise_cross_frequency")
    if isinstance(pairwise, Mapping) and pairwise.get("available", True):
        axes = _record_axes(pairwise, "comparisons.pairwise_cross_frequency", errors, warnings)
        add("pairwise_cross_frequency", "pairwise_cross_frequency_magnitude", pairwise, pairwise.get("magnitude"), {"left": axes["frequency"], "right": axes["frequency"]}, nonnegative=True, expected_shape=(len(axes["frequency"]["frequencies_hz"]), len(axes["frequency"]["frequencies_hz"])), metadata_extra={"segment_count": pairwise.get("segment_count"), "method": pairwise.get("method")})

    controls = _surrogate_controls(report)
    if not controls:
        warnings.append("no surrogate comparison controls were supplied")
    return SpectralFeatureContract(SCHEMA_VERSION, evidence, synthetic, checksum, tuple(records), tuple(sorted(set(errors))), tuple(sorted(set(warnings))))


def contract_to_json(contract: SpectralFeatureContract) -> str:
    return json.dumps(contract.to_dict(), sort_keys=True, indent=2, allow_nan=False)


def contract_to_markdown(contract: SpectralFeatureContract) -> str:
    lines = [
        "# Spectral feature contract",
        "",
        f"- Schema: `{contract.schema_version}`",
        f"- Evidence class: `{contract.evidence_class}`",
        f"- Synthetic: `{contract.synthetic}`",
        f"- Source checksum: `{contract.source_checksum_sha256 or 'null'}`",
        "",
        "| Feature family | Shape | Sampling rate (Hz) | Filtering | Synthetic | Errors |",
        "|---|---:|---:|---|---|---:|",
    ]
    for record in contract.records:
        metadata = record.metadata
        lines.append(
            f"| {record.feature_family} | `{record.value_shape}` | {metadata.get('sampling_rate_hz')} | "
            f"{record.filtering_status} | {metadata.get('synthetic')} | {len(record.errors)} |"
        )
    lines.extend(["", "## Validation", "", f"- Errors: {len(contract.validation_errors)}", f"- Warnings: {len(contract.validation_warnings)}", "", "Higher-order spectral structure is descriptive signal-processing evidence, not topology, causality, biological evidence, or consciousness evidence.", ""])
    return "\n".join(lines)


# Short aliases for downstream scripts that use validator/adapter terminology.
adapt_report = adapt_spectral_feature_report
validate_report = validate_spectral_feature_report
