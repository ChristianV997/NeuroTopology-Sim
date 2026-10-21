"""Unit tests for strict RFC 8259 finite JSON serialization and SHA-256 integrity digests."""
from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path
import pytest

from analysis.serialization import (
    dumps_rfc8259,
    verify_telemetry_digest,
    write_canonical_telemetry,
)


class TestRFC8259Serialization:
    def test_finite_values_succeed(self):
        """Finite values, nested structures, and numbers serialize with deterministic sorted keys."""
        data = {
            "zeta": 1.25,
            "alpha": [1, 2, 3],
            "beta": {"sub": 0.0, "null_field": None, "flag": True},
        }
        res = dumps_rfc8259(data)
        loaded = json.loads(res)
        assert loaded["zeta"] == 1.25
        assert loaded["beta"]["flag"] is True

        # Assert sorted keys order
        lines = res.splitlines()
        assert any('"alpha":' in l for l in lines)

    @pytest.mark.parametrize("bad_val", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_values_rejected(self, bad_val):
        """Any NaN or Infinity must immediately raise ValueError."""
        data = {"metric": bad_val}
        with pytest.raises(ValueError) as exc_info:
            dumps_rfc8259(data)
        assert "Non-finite" in str(exc_info.value) or "RFC 8259" in str(exc_info.value)


class TestTelemetryIntegrity:
    def test_digest_write_and_verify_roundtrip(self):
        """Companion .sha256 file must verify cleanly and fail on tampered content."""
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "benchmark_test.json"
            payload = {"runtime_s": 0.42, "status": "SUCCESS", "records": [10, 20]}

            json_path, digest = write_canonical_telemetry(target, payload)
            assert json_path.is_file()
            sha_path = json_path.with_suffix(json_path.suffix + ".sha256")
            assert sha_path.is_file()

            # 1. Valid verification
            valid, msg = verify_telemetry_digest(json_path)
            assert valid is True
            assert digest in msg

            # 2. Tampering test
            tampered = json_path.read_text(encoding="utf-8").replace("0.42", "9.99")
            json_path.write_text(tampered, encoding="utf-8")

            valid2, msg2 = verify_telemetry_digest(json_path)
            assert valid2 is False
            assert "Checksum mismatch" in msg2
