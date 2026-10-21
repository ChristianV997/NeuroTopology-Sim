"""Finite JSON — reject NaN / Infinity."""
from __future__ import annotations

import json
import math

import pytest

from tools.release_readiness.batch2_security import fixtures as fx
from tools.release_readiness.batch2_security.finite_json import (
    NonFiniteJSONError,
    dumps_finite,
    dumps_strict,
)
from tools.release_readiness.batch2_security.schema import json_safe


def test_strict_rejects_nan_and_infinity():
    with pytest.raises(NonFiniteJSONError):
        dumps_strict(fx.NON_FINITE_PAYLOAD)


def test_finite_payload_roundtrips():
    text = dumps_strict(fx.FINITE_PAYLOAD)
    assert "NaN" not in text
    assert "Infinity" not in text
    assert json.loads(text)["score"] == 1.25


def test_json_safe_coerces_non_finite_to_null():
    cleaned = json_safe({"x": float("nan"), "y": float("inf"), "z": 1.0})
    assert cleaned["x"] is None
    assert cleaned["y"] is None
    assert cleaned["z"] == 1.0
    text = dumps_finite(cleaned)
    json.loads(text)  # allow_nan=False path already applied
