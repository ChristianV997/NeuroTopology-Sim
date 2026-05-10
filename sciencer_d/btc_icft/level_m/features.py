import math
from collections import Counter


def _safe_mean(x: list[float]) -> float:
    return sum(x) / len(x) if x else 0.0


def extract_level_m_features(signal: list[float]) -> dict[str, float]:
    n = len(signal)
    if n == 0:
        return {
            "spectral_power_proxy": 0.0,
            "entropy_proxy": 0.0,
            "lzc_proxy": 0.0,
            "artifact_score": 1.0,
        }

    spectral_power_proxy = _safe_mean([v * v for v in signal])

    hist = Counter(round(v, 1) for v in signal)
    entropy_proxy = 0.0
    for c in hist.values():
        p = c / n
        entropy_proxy -= p * math.log2(p)

    symbolic = ''.join('1' if v >= _safe_mean(signal) else '0' for v in signal)
    lzc_proxy = len({symbolic[i:j] for i in range(n) for j in range(i + 1, min(n, i + 4) + 1)}) / max(n, 1)

    jumps = [abs(signal[i] - signal[i - 1]) for i in range(1, n)]
    artifact_score = min(1.0, _safe_mean(jumps) / (abs(_safe_mean(signal)) + 1e-6)) if jumps else 0.0

    return {
        "spectral_power_proxy": spectral_power_proxy,
        "entropy_proxy": entropy_proxy,
        "lzc_proxy": lzc_proxy,
        "artifact_score": artifact_score,
    }
