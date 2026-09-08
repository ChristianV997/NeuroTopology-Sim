"""Bounded higher-order spectral estimators.

This module deliberately exposes signal-processing summaries only.  A
bispectral or modulogram pattern is not a topological invariant, a causal
claim, or evidence about consciousness.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import replace
from typing import Any, Callable, Iterable, Optional

import numpy as np

from .spectral_types import (
    SCHEMA_VERSION,
    BispectrumSummary,
    FrequencyAxis,
    HigherOrderSpectralReport,
    Modulogram,
    Provenance,
    SegmentConfiguration,
    SurrogateComparison,
    TrispectrumSlice,
)


def _finite(value: Any) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _array(signal: Any, config: SegmentConfiguration) -> np.ndarray:
    data = np.asarray(signal, dtype=float)
    if data.ndim == 1:
        data = data[None, :]
    if data.ndim != 2 or data.shape[1] < 2:
        raise ValueError("signal must be a finite 1-D or channels-by-samples 2-D array")
    if not np.all(np.isfinite(data)):
        raise ValueError("signal contains NaN or Infinity")
    if data.shape[0] > config.max_channels:
        raise ValueError(f"channel count exceeds max_channels={config.max_channels}")
    return np.ascontiguousarray(data)


def _validate_config(config: SegmentConfiguration) -> None:
    if config.segment_length < 2 or config.n_fft < config.segment_length:
        raise ValueError("n_fft must be >= segment_length >= 2")
    if not 0.0 <= config.overlap < 1.0:
        raise ValueError("overlap must satisfy 0 <= overlap < 1")
    if config.taper not in {"boxcar", "hann", "hamming", "blackman"}:
        raise ValueError("taper must be boxcar, hann, hamming, or blackman")
    if config.detrend not in {"none", "constant", "linear"}:
        raise ValueError("detrend must be none, constant, or linear")
    if config.frequency_bins < 2 or config.frequency_bins > config.n_fft // 2 + 1:
        raise ValueError("frequency_bins exceeds the configured FFT axis")
    if config.trispectrum_slices < 1 or config.trispectrum_slices > config.frequency_bins - 1:
        raise ValueError("trispectrum_slices must fit within frequency_bins")
    if config.max_channels < 1 or config.memory_budget_bytes <= 0:
        raise ValueError("max_channels and memory_budget_bytes are too small")
    if config.max_surrogates < 0:
        raise ValueError("max_surrogates must be non-negative")


def _validate_sampling_rate(sampling_rate_hz: float) -> float:
    rate = _finite(sampling_rate_hz)
    if rate is None or rate <= 0.0:
        raise ValueError("sampling_rate_hz must be finite and strictly positive")
    return rate


def _segment_starts(n_samples: int, config: SegmentConfiguration) -> tuple[int, ...]:
    step = max(1, int(round(config.segment_length * (1.0 - config.overlap))))
    if n_samples <= config.segment_length:
        return (0,)
    return tuple(range(0, n_samples - config.segment_length + 1, step))


def _estimated_memory_bytes(data: np.ndarray, config: SegmentConfiguration) -> int:
    segments = len(_segment_starts(data.shape[1], config))
    # Input, two complex FFT workspaces, and bounded output accumulators.
    return int(data.nbytes + segments * data.shape[0] * config.n_fft * 32)


def _check_budget(data: np.ndarray, config: SegmentConfiguration) -> None:
    estimate = _estimated_memory_bytes(data, config)
    if estimate > config.memory_budget_bytes:
        raise MemoryError(
            f"estimated working memory {estimate} exceeds "
            f"memory_budget_bytes={config.memory_budget_bytes}"
        )


def _window(config: SegmentConfiguration) -> np.ndarray:
    n = config.segment_length
    if config.taper == "boxcar":
        return np.ones(n, dtype=float)
    if config.taper == "hann":
        return np.hanning(n)
    if config.taper == "hamming":
        return np.hamming(n)
    return np.blackman(n)


def _preprocess(segment: np.ndarray, config: SegmentConfiguration, window: np.ndarray) -> np.ndarray:
    result = np.asarray(segment, dtype=float).copy()
    scale = float(np.max(np.abs(result)))
    if scale > 0.0:
        result /= scale
    if config.detrend == "linear":
        x = np.linspace(-1.0, 1.0, result.size)
        design = np.column_stack((np.ones(result.size), x))
        result -= design @ np.linalg.lstsq(design, result, rcond=None)[0]
    elif config.detrend == "constant" or config.demean:
        result -= float(np.mean(result))
    result *= window
    rms = float(np.sqrt(np.mean(result * result)))
    if rms > 0.0 and math.isfinite(rms):
        result /= rms
    return result


def _fft_segments(data: np.ndarray, config: SegmentConfiguration) -> Iterable[np.ndarray]:
    window = _window(config)
    for start in _segment_starts(data.shape[1], config):
        stop = start + config.segment_length
        for channel in data:
            segment = channel[start:stop]
            if segment.size < config.segment_length:
                segment = np.pad(segment, (0, config.segment_length - segment.size))
            yield np.fft.rfft(_preprocess(segment, config, window), n=config.n_fft)


def _axis(config: SegmentConfiguration, sampling_rate_hz: float) -> FrequencyAxis:
    resolution = sampling_rate_hz / config.n_fft
    frequencies = tuple(float(i * resolution) for i in range(config.frequency_bins))
    return FrequencyAxis(
        frequencies_hz=frequencies,
        resolution_hz=float(resolution),
        nyquist_hz=float(sampling_rate_hz / 2.0),
    )


def _config_or_default(config: SegmentConfiguration | None) -> SegmentConfiguration:
    result = config or SegmentConfiguration()
    _validate_config(result)
    return result


def make_provenance(
    signal: Any,
    sampling_rate_hz: float,
    *,
    synthetic: bool = False,
    source: str = "in_memory",
) -> Provenance:
    """Create deterministic provenance from the normalized signal bytes."""
    rate = _validate_sampling_rate(sampling_rate_hz)
    data = np.asarray(signal, dtype=np.float64)
    if data.ndim == 1:
        shape = (1, data.size)
    elif data.ndim == 2:
        shape = data.shape
    else:
        raise ValueError("signal must be 1-D or 2-D")
    if not np.all(np.isfinite(data)):
        raise ValueError("signal contains NaN or Infinity")
    canonical = np.ascontiguousarray(data).tobytes()
    digest = hashlib.sha256(
        repr((shape, rate)).encode("utf-8") + b"\0" + canonical
    ).hexdigest()
    return Provenance(
        source=str(source),
        sampling_rate_hz=rate,
        synthetic=bool(synthetic),
        checksum_sha256=digest,
        n_channels=int(shape[0]),
        n_samples=int(shape[1]),
    )


def compute_bispectrum(
    signal: Any,
    sampling_rate_hz: float,
    *,
    config: SegmentConfiguration | None = None,
) -> BispectrumSummary:
    """Estimate a bounded channel-averaged bispectrum and bicoherence."""
    cfg = _config_or_default(config)
    rate = _validate_sampling_rate(sampling_rate_hz)
    data = _array(signal, cfg)
    _check_budget(data, cfg)
    bins = cfg.frequency_bins
    complex_sum = np.zeros((bins, bins), dtype=complex)
    product_power = np.zeros((bins, bins), dtype=float)
    third_power = np.zeros((bins, bins), dtype=float)
    valid = np.zeros((bins, bins), dtype=bool)
    segments = _segment_starts(data.shape[1], cfg)
    for index, spectrum in enumerate(_fft_segments(data, cfg)):
        i = index % data.shape[0]
        del i  # The loop is channel-major; all channels contribute equally.
        for first in range(bins):
            for second in range(bins):
                third = first + second
                if third >= spectrum.size:
                    continue
                product = spectrum[first] * spectrum[second] * np.conj(spectrum[third])
                complex_sum[first, second] += product
                product_power[first, second] += abs(spectrum[first] * spectrum[second]) ** 2
                third_power[first, second] += abs(spectrum[third]) ** 2
                valid[first, second] = True
    divisor = max(1, len(segments) * data.shape[0])
    magnitude = np.abs(complex_sum / divisor)
    bicoherence = np.zeros_like(magnitude)
    denominator = product_power * third_power
    nonzero = valid & (denominator > 0.0)
    bicoherence[nonzero] = np.minimum(
        1.0, (np.abs(complex_sum[nonzero]) ** 2) / denominator[nonzero]
    )
    magnitude_out = tuple(
        tuple(_finite(magnitude[i, j]) if valid[i, j] else None for j in range(bins))
        for i in range(bins)
    )
    coherence_out = tuple(
        tuple(_finite(bicoherence[i, j]) if valid[i, j] else None for j in range(bins))
        for i in range(bins)
    )
    return BispectrumSummary(
        frequency_axis=_axis(cfg, rate),
        magnitude=magnitude_out,
        bicoherence=coherence_out,
        segment_count=len(segments),
        channel_count=data.shape[0],
        normalization="RMS-normalized segments; bicoherence in [0, 1]",
    )


def compute_trispectrum_slices(
    signal: Any,
    sampling_rate_hz: float,
    *,
    config: SegmentConfiguration | None = None,
    slice_frequencies_hz: Iterable[float] | None = None,
) -> TrispectrumSlice:
    """Estimate selected two-dimensional trispectrum slices only."""
    cfg = _config_or_default(config)
    rate = _validate_sampling_rate(sampling_rate_hz)
    data = _array(signal, cfg)
    _check_budget(data, cfg)
    axis = _axis(cfg, rate)
    if slice_frequencies_hz is None:
        slice_indices = np.linspace(1, cfg.frequency_bins - 1, cfg.trispectrum_slices, dtype=int)
        slice_indices = tuple(dict.fromkeys(int(value) for value in slice_indices))
    else:
        requested = tuple(float(value) for value in slice_frequencies_hz)
        if len(requested) > cfg.trispectrum_slices:
            raise ValueError("requested slice count exceeds trispectrum_slices")
        slice_indices = tuple(
            min(range(cfg.frequency_bins), key=lambda index: abs(axis.frequencies_hz[index] - value))
            for value in requested
        )
    if not slice_indices:
        raise ValueError("at least one trispectrum slice is required")
    bins = cfg.frequency_bins
    sums = np.zeros((len(slice_indices), bins, bins), dtype=complex)
    valid = np.zeros_like(sums, dtype=bool)
    segments = _segment_starts(data.shape[1], cfg)
    for index, spectrum in enumerate(_fft_segments(data, cfg)):
        del index
        for slice_index, first in enumerate(slice_indices):
            for second in range(bins):
                for third in range(bins):
                    fourth = first + second + third
                    if fourth >= spectrum.size:
                        continue
                    sums[slice_index, second, third] += (
                        spectrum[first] * spectrum[second] * spectrum[third] * np.conj(spectrum[fourth])
                    )
                    valid[slice_index, second, third] = True
    divisor = max(1, len(segments) * data.shape[0])
    magnitude = np.abs(sums / divisor)
    output = tuple(
        tuple(
            tuple(_finite(magnitude[slice_index, second, third])
                  if valid[slice_index, second, third] else None for third in range(bins))
            for second in range(bins)
        )
        for slice_index in range(len(slice_indices))
    )
    return TrispectrumSlice(
        frequency_axis=axis,
        slice_frequencies_hz=tuple(axis.frequencies_hz[index] for index in slice_indices),
        magnitude=output,
        segment_count=len(segments),
        normalization="RMS-normalized segments; selected slices only",
    )


def _analytic_envelope(
    segment: np.ndarray, carrier_index: int, n_fft: int, bandwidth_bins: int = 2
) -> np.ndarray:
    spectrum = np.fft.fft(segment, n=n_fft)
    mask = np.zeros(n_fft, dtype=float)
    low = max(1, carrier_index - bandwidth_bins)
    high = min(n_fft // 2, carrier_index + bandwidth_bins)
    mask[low:high + 1] = 2.0
    mask[0] = 1.0
    if n_fft % 2 == 0:
        mask[n_fft // 2] = 1.0
    mask[-high + 1:-low + 1] = 0.0
    return np.abs(np.fft.ifft(spectrum * mask))


def compute_modulogram(
    signal: Any,
    sampling_rate_hz: float,
    *,
    config: SegmentConfiguration | None = None,
) -> Modulogram:
    """Compute a reduced carrier-by-modulation-frequency representation."""
    cfg = _config_or_default(config)
    rate = _validate_sampling_rate(sampling_rate_hz)
    data = _array(signal, cfg)
    _check_budget(data, cfg)
    axis = _axis(cfg, rate)
    bins = cfg.frequency_bins
    accum = np.zeros((bins, bins), dtype=float)
    segments = _segment_starts(data.shape[1], cfg)
    window = _window(cfg)
    sideband_width_bins = max(2, int(round(5.0 / axis.resolution_hz)))
    for channel in data:
        for start in segments:
            stop = start + cfg.segment_length
            segment = channel[start:stop]
            if segment.size < cfg.segment_length:
                segment = np.pad(segment, (0, cfg.segment_length - segment.size))
            prepared = _preprocess(segment, cfg, window)
            for carrier in range(1, bins):
                envelope = _analytic_envelope(
                    prepared, carrier, cfg.n_fft, bandwidth_bins=sideband_width_bins
                )
                envelope -= float(np.mean(envelope))
                modulation = np.abs(np.fft.rfft(envelope, n=cfg.n_fft)[:bins])
                scale = float(np.sum(modulation))
                if scale > 0.0 and math.isfinite(scale):
                    accum[carrier] += modulation / scale
    divisor = max(1, len(segments) * data.shape[0])
    values = accum / divisor
    output = tuple(
        tuple(_finite(values[carrier, modulation]) for modulation in range(bins))
        for carrier in range(bins)
    )
    return Modulogram(
        carrier_axis=axis,
        modulation_axis=axis,
        magnitude=output,
        segment_count=len(segments),
        normalization="RMS-normalized segments; each carrier row L1-normalized",
    )


def power_spectral_density(
    signal: Any,
    sampling_rate_hz: float,
    *,
    config: SegmentConfiguration | None = None,
) -> dict[str, Any]:
    """Return a bounded PSD comparison feature."""
    cfg = _config_or_default(config)
    rate = _validate_sampling_rate(sampling_rate_hz)
    data = _array(signal, cfg)
    _check_budget(data, cfg)
    bins = cfg.frequency_bins
    total = np.zeros(bins, dtype=float)
    segments = _segment_starts(data.shape[1], cfg)
    for spectrum in _fft_segments(data, cfg):
        total += np.abs(spectrum[:bins]) ** 2
    divisor = max(1, len(segments) * data.shape[0])
    return {
        "frequency_axis": _axis(cfg, rate).to_dict(),
        "power": [_finite(value / divisor) for value in total],
        "segment_count": len(segments),
        "normalization": "RMS-normalized segments",
    }


def cross_spectrum(
    signal: Any,
    sampling_rate_hz: float,
    *,
    config: SegmentConfiguration | None = None,
) -> dict[str, Any]:
    """Return the first-pair cross-spectrum comparison feature."""
    cfg = _config_or_default(config)
    rate = _validate_sampling_rate(sampling_rate_hz)
    data = _array(signal, cfg)
    if data.shape[0] < 2:
        return {"available": False, "reason": "at least two channels are required"}
    _check_budget(data, cfg)
    bins = cfg.frequency_bins
    total = np.zeros(bins, dtype=complex)
    segments = _segment_starts(data.shape[1], cfg)
    window = _window(cfg)
    for start in segments:
        spectra = []
        for channel in data[:2]:
            stop = start + cfg.segment_length
            segment = channel[start:stop]
            if segment.size < cfg.segment_length:
                segment = np.pad(segment, (0, cfg.segment_length - segment.size))
            spectra.append(np.fft.rfft(_preprocess(segment, cfg, window), n=cfg.n_fft))
        total += spectra[0][:bins] * np.conj(spectra[1][:bins])
    mean = total / max(1, len(segments))
    return {
        "available": True,
        "frequency_axis": _axis(cfg, rate).to_dict(),
        "magnitude": [_finite(abs(value)) for value in mean],
        "phase_radians": [_finite(np.angle(value)) for value in mean],
        "segment_count": len(segments),
    }


def _band_analytic(signal: np.ndarray, sampling_rate_hz: float, band: tuple[float, float]) -> np.ndarray:
    n = signal.size
    frequencies = np.fft.fftfreq(n, d=1.0 / sampling_rate_hz)
    spectrum = np.fft.fft(signal)
    mask = (frequencies >= band[0]) & (frequencies <= band[1])
    filtered = np.zeros_like(spectrum)
    filtered[mask] = 2.0 * spectrum[mask]
    return np.fft.ifft(filtered)


def phase_amplitude_coupling(
    signal: Any,
    sampling_rate_hz: float,
    *,
    phase_band: tuple[float, float] = (4.0, 8.0),
    amplitude_band: tuple[float, float] = (30.0, 80.0),
) -> dict[str, Any]:
    """Return a simple normalized phase-amplitude coupling comparison."""
    rate = _validate_sampling_rate(sampling_rate_hz)
    data = np.asarray(signal, dtype=float)
    if data.ndim == 2:
        data = data[0]
    if data.ndim != 1 or data.size < 4 or not np.all(np.isfinite(data)):
        raise ValueError("signal must contain a finite one-dimensional series")
    phase = np.angle(_band_analytic(data, rate, phase_band))
    amplitude = np.abs(_band_analytic(data, rate, amplitude_band))
    mean_amplitude = float(np.mean(amplitude))
    value = 0.0 if mean_amplitude == 0.0 else abs(np.mean(amplitude * np.exp(1j * phase))) / mean_amplitude
    return {
        "available": True,
        "phase_band_hz": list(phase_band),
        "amplitude_band_hz": list(amplitude_band),
        "modulation_index": _finite(value),
        "method": "mean-vector-length proxy",
    }


def pairwise_cross_frequency_metrics(
    signal: Any,
    sampling_rate_hz: float,
    *,
    config: SegmentConfiguration | None = None,
) -> dict[str, Any]:
    """Return a bounded cross-channel frequency-pair magnitude matrix."""
    cfg = _config_or_default(config)
    rate = _validate_sampling_rate(sampling_rate_hz)
    data = _array(signal, cfg)
    if data.shape[0] < 2:
        return {"available": False, "reason": "at least two channels are required"}
    _check_budget(data, cfg)
    bins = cfg.frequency_bins
    accum = np.zeros((bins, bins), dtype=complex)
    segments = _segment_starts(data.shape[1], cfg)
    window = _window(cfg)
    for start in segments:
        spectra = []
        for channel in data[:2]:
            segment = channel[start:start + cfg.segment_length]
            if segment.size < cfg.segment_length:
                segment = np.pad(segment, (0, cfg.segment_length - segment.size))
            spectra.append(np.fft.rfft(_preprocess(segment, cfg, window), n=cfg.n_fft))
        accum += spectra[0][:bins, None] * np.conj(spectra[1][None, :bins])
    values = np.abs(accum / max(1, len(segments)))
    return {
        "available": True,
        "frequency_axis": _axis(cfg, rate).to_dict(),
        "magnitude": [[_finite(value) for value in row] for row in values],
        "segment_count": len(segments),
        "method": "pairwise cross-frequency magnitude proxy",
    }


def _amplitude_shuffle(data: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    result = np.empty_like(data)
    for index, channel in enumerate(data):
        result[index] = channel[rng.permutation(channel.size)]
    return result


def _phase_randomized(data: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    result = np.empty_like(data)
    for index, channel in enumerate(data):
        spectrum = np.fft.rfft(channel)
        phase = rng.uniform(-np.pi, np.pi, size=spectrum.size)
        phase[0] = 0.0
        if channel.size % 2 == 0:
            phase[-1] = 0.0
        result[index] = np.fft.irfft(np.abs(spectrum) * np.exp(1j * phase), n=channel.size)
    return result


def _block_shuffle(data: np.ndarray, rng: np.random.Generator, block_length: int) -> np.ndarray:
    if block_length < 1:
        raise ValueError("block_length must be positive")
    result = np.empty_like(data)
    for index, channel in enumerate(data):
        blocks = [channel[start:start + block_length] for start in range(0, channel.size, block_length)]
        order = rng.permutation(len(blocks))
        result[index] = np.concatenate([blocks[item] for item in order])[:channel.size]
    return result


def amplitude_shuffle_surrogate(signal: Any, *, seed: int = 0) -> np.ndarray:
    data = np.asarray(signal, dtype=float)
    if data.ndim == 1:
        data = data[None, :]
    return _amplitude_shuffle(data, np.random.default_rng(seed))


def phase_randomized_surrogate(signal: Any, *, seed: int = 0) -> np.ndarray:
    data = np.asarray(signal, dtype=float)
    if data.ndim == 1:
        data = data[None, :]
    return _phase_randomized(data, np.random.default_rng(seed))


def block_shuffle_surrogate(signal: Any, *, block_length: int, seed: int = 0) -> np.ndarray:
    data = np.asarray(signal, dtype=float)
    if data.ndim == 1:
        data = data[None, :]
    return _block_shuffle(data, np.random.default_rng(seed), block_length)


def compare_against_surrogates(
    signal: Any,
    sampling_rate_hz: float,
    *,
    method: str = "phase_randomized",
    n_surrogates: int = 16,
    seed: int = 0,
    block_length: int | None = None,
    config: SegmentConfiguration | None = None,
) -> SurrogateComparison:
    """Compare modulogram peak strength against deterministic surrogates."""
    cfg = _config_or_default(config)
    if n_surrogates < 1 or n_surrogates > cfg.max_surrogates:
        raise ValueError("n_surrogates must be within the configured bound")
    data = _array(signal, cfg)
    rng = np.random.default_rng(seed)
    observed_map = compute_modulogram(data, sampling_rate_hz, config=cfg).magnitude
    observed_values = [value for row in observed_map for value in row if value is not None]
    observed = max(observed_values) if observed_values else None
    surrogate_values: list[float] = []
    for _ in range(n_surrogates):
        if method == "amplitude_shuffle":
            surrogate = _amplitude_shuffle(data, rng)
        elif method == "phase_randomized":
            surrogate = _phase_randomized(data, rng)
        elif method == "block_shuffle":
            surrogate = _block_shuffle(data, rng, block_length or cfg.segment_length)
        else:
            raise ValueError("unknown surrogate method")
        values = compute_modulogram(surrogate, sampling_rate_hz, config=cfg).magnitude
        finite_values = [value for row in values for value in row if value is not None]
        if finite_values:
            surrogate_values.append(float(max(finite_values)))
    if not surrogate_values or observed is None:
        return SurrogateComparison(method, seed, n_surrogates, observed, None, None, None, None, block_length)
    mean = float(np.mean(surrogate_values))
    std = float(np.std(surrogate_values, ddof=1)) if len(surrogate_values) > 1 else 0.0
    standardized = None if std == 0.0 else _finite((observed - mean) / std)
    p_value = (1.0 + sum(value >= observed for value in surrogate_values)) / (len(surrogate_values) + 1.0)
    return SurrogateComparison(
        method=method,
        seed=int(seed),
        surrogate_count=len(surrogate_values),
        observed=_finite(observed),
        surrogate_mean=_finite(mean),
        surrogate_std=_finite(std),
        standardized_difference=standardized,
        empirical_p_value=_finite(p_value),
        block_length=block_length,
    )


def _diagnostics(
    data: np.ndarray,
    config: SegmentConfiguration,
    modulogram: Modulogram,
) -> dict[str, Any]:
    values = [value for row in modulogram.magnitude for value in row if value is not None]
    peak = max(values) if values else None
    return {
        "gaussian_noise_behavior": "higher-order estimates should approach zero for independent Gaussian noise; no null claim is made",
        "amplitude_modulated_carrier": {"modulogram_peak": peak, "interpretation": "descriptive modulation feature"},
        "coupled_oscillator_proxy": "cross-channel comparison is required; no causal inference",
        "filter_induced_artifact_warning": "finite tapers and band limits can create peaks; inspect taper and segment sensitivity",
        "edge_effect_warning": "finite segments and analytic-envelope boundaries can bias edge bins",
        "segment_count_instability": len(_segment_starts(data.shape[1], config)) < 4,
        "segment_count": len(_segment_starts(data.shape[1], config)),
    }


def compute_higher_order_spectra(
    signal: Any,
    sampling_rate_hz: float,
    *,
    config: SegmentConfiguration | None = None,
    source: str = "in_memory",
    synthetic: bool = False,
    surrogate_methods: Iterable[str] = (),
    surrogate_count: int = 0,
    seed: int = 0,
) -> HigherOrderSpectralReport:
    """Compute bounded higher-order spectra and comparison metadata."""
    cfg = _config_or_default(config)
    data = _array(signal, cfg)
    rate = _validate_sampling_rate(sampling_rate_hz)
    _check_budget(data, cfg)
    bispectrum = compute_bispectrum(data, rate, config=cfg)
    trispectrum = compute_trispectrum_slices(data, rate, config=cfg)
    modulogram = compute_modulogram(data, rate, config=cfg)
    comparisons = {
        "psd": power_spectral_density(data, rate, config=cfg),
        "cross_spectrum": cross_spectrum(data, rate, config=cfg),
        "phase_amplitude_coupling": phase_amplitude_coupling(data[0], rate),
        "pairwise_cross_frequency": pairwise_cross_frequency_metrics(data, rate, config=cfg),
    }
    surrogates = tuple(
        compare_against_surrogates(
            data, rate, method=method, n_surrogates=surrogate_count,
            seed=seed + offset, config=cfg,
        )
        for offset, method in enumerate(surrogate_methods)
    ) if surrogate_count else ()
    return HigherOrderSpectralReport(
        schema_version=SCHEMA_VERSION,
        provenance=make_provenance(data, rate, synthetic=synthetic, source=source),
        segment_configuration=cfg,
        bispectrum=bispectrum,
        trispectrum=trispectrum,
        modulogram=modulogram,
        comparisons=comparisons,
        surrogates=surrogates,
        diagnostics=_diagnostics(data, cfg, modulogram),
        warnings=("Higher-order spectral structure is signal-processing evidence, not topology or consciousness evidence.",),
    )


def report_to_json(report: HigherOrderSpectralReport) -> str:
    """Serialize a report with NaN/Infinity rejected."""
    return json.dumps(report.to_dict(), sort_keys=True, allow_nan=False, indent=2)


# Explicit aliases make the estimator names discoverable without changing the
# typed records returned by the canonical compute_* functions.
estimate_bispectrum = compute_bispectrum
estimate_trispectrum_slices = compute_trispectrum_slices
estimate_modulogram = compute_modulogram
