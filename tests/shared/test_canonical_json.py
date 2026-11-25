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
