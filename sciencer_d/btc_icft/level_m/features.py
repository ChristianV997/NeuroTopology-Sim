import math
from collections import Counter


def _safe_mean(x: list[float]) -> float:
    return sum(x) / len(x) if x else 0.0


def _safe_std(x: list[float], mean: float) -> float:
    if not x:
        return 0.0
    return math.sqrt(sum((v - mean) ** 2 for v in x) / len(x))


def extract_level_m_features(signal: list[float]) -> dict[str, float]:
    n = len(signal)
    if n == 0:
        return {
            "spectral_power_proxy": 0.0,
            "entropy_proxy": 0.0,
            "lzc_proxy": 0.0,
            "artifact_score": 1.0,
        }

    signal_mean = _safe_mean(signal)
    spectral_power_proxy = _safe_mean([v * v for v in signal])

    hist = Counter(round(v, 1) for v in signal)
    entropy_proxy = 0.0
    for c in hist.values():
        p = c / n
        entropy_proxy -= p * math.log2(p)

    symbolic = ''.join('1' if v >= signal_mean else '0' for v in signal)
    lzc_proxy = len({symbolic[i:j] for i in range(n) for j in range(i + 1, min(n, i + 4) + 1)}) / n

    # Scale-invariant "jump index": ratio of typical sample-to-sample jump size to the
    # signal's own spread (std). Deliberately NOT normalized by signal_mean: for a
    # zero-mean signal (e.g. after z-normalization) that denominator is ~0 by
    # construction, which previously made this saturate to 1.0 for every window
    # regardless of actual signal quality.
    signal_std = _safe_std(signal, signal_mean)
    jumps = [abs(signal[i] - signal[i - 1]) for i in range(1, n)]
    artifact_score = min(1.0, _safe_mean(jumps) / (signal_std + 1e-6)) if jumps else 0.0

    return {
        "spectral_power_proxy": spectral_power_proxy,
        "entropy_proxy": entropy_proxy,
        "lzc_proxy": lzc_proxy,
        "artifact_score": artifact_score,
    }
