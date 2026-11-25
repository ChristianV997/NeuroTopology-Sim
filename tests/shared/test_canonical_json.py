"""Golden vectors: shared.canonical_json must keep the legacy bytes that feed stored hashes."""
import hashlib
import importlib
import math
from pathlib import Path

import pytest

from shared.canonical_json import canonical_json_text

MIGRATED = [
    "benchmark_packs.gallery", "benchmark_packs.gallery_renderer", "benchmark_packs.pack_manifest",
    "benchmark_packs.pack_spec", "benchmark_packs.verification", "evidence.bundle",
    "job_runner.batch_manifest", "job_runner.job", "job_runner.queue", "job_runner.result",
    "job_runner.worker", "phase_space.coordinate", "reports.evidence_report", "transitions.record",
    "workflows.html_report_pack", "workflows.report_pack", "workflows.report_pipeline",
]


def test_golden_bytes():
    value = {"b": [1, 2.5, None], "a": "é", "p": Path("x/y"), "n": float("nan")}
    text = canonical_json_text(value)
    assert text == '{"a":"\\u00e9","b":[1,2.5,null],"n":NaN,"p":"x/y"}'
    assert hashlib.sha256(text.encode()).hexdigest()[:16] == hashlib.sha256(
        b'{"a":"\\u00e9","b":[1,2.5,null],"n":NaN,"p":"x/y"}').hexdigest()[:16]


def test_strict_mode_rejects_non_rfc8259_values():
    with pytest.raises(ValueError):
        canonical_json_text({"x": math.inf}, strict=True)
    with pytest.raises(TypeError):
        canonical_json_text({"p": Path("x")}, strict=True)
    assert canonical_json_text({"b": 1, "a": [True]}, strict=True) == '{"a":[true],"b":1}'


@pytest.mark.parametrize("module", MIGRATED)
def test_migrated_modules_use_the_shared_helper(module):
    assert importlib.import_module(module)._canonical_json is canonical_json_text


def test_strict_non_ascii_golden_bytes():
    value = {"z": "é→", "a": [1.5, -0.0]}
    assert canonical_json_text(value, strict=True, ensure_ascii=False) == '{"a":[1.5,-0.0],"z":"é→"}'
    assert canonical_json_text(value, strict=True) == '{"a":[1.5,-0.0],"z":"\\u00e9\\u2192"}'


def _random_json(rng, depth=0):
    kind = rng.randrange(7 if depth < 4 else 4)
    if kind == 0:
        return rng.choice([None, True, False])
    if kind == 1:
        return rng.randint(-10**12, 10**12)
    if kind == 2:
        return rng.uniform(-1e6, 1e6)
    if kind == 3:
        return "".join(rng.choice("abé→\U0001f600\"\\\n ") for _ in range(rng.randrange(6)))
    if kind in (4, 5):
        return [_random_json(rng, depth + 1) for _ in range(rng.randrange(4))]
    return {str(_random_json(rng, 4)): _random_json(rng, depth + 1) for _ in range(rng.randrange(4))}


@pytest.mark.parametrize("ensure_ascii", [True, False])
def test_strict_mode_is_byte_identical_to_the_replaced_inline_encoders(ensure_ascii):
    # Eleven modules (interop contracts, research envelope, triadic, SU(2) sweep, PITNN bridge,
    # plan-quality records, streaming checkpoints, source packs, batch3, triadic adapter,
    # transition benchmark) replaced exactly this json.dumps call; their hashes depend on it.
    import json
    import random

    rng = random.Random(20261125)
    for _ in range(500):
        value = _random_json(rng)
        expected = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=ensure_ascii)
        assert canonical_json_text(value, strict=True, ensure_ascii=ensure_ascii) == expected
