"""Finite JSON helpers — reject NaN / Infinity serialization."""
from __future__ import annotations

import json
import math
from typing import Any

from tools.release_readiness.batch2_security.schema import (
    REMEDIATION_OWNERS,
    Finding,
    ThreatClass,
    json_safe,
)


class NonFiniteJSONError(ValueError):
    """Raised when a payload contains non-finite floats."""


def assert_finite(value: Any, *, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise NonFiniteJSONError(f"non-finite float at {path}: {value!r}")
    if isinstance(value, dict):
        for key, item in value.items():
            assert_finite(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            assert_finite(item, path=f"{path}[{index}]")


def dumps_finite(obj: Any, *, indent: int | None = 2) -> str:
    """Serialize with allow_nan=False after json_safe coercion of non-finites to null.

    Callers that need strict rejection (no coercion) should use ``assert_finite``
    before calling this helper, or ``dumps_strict``.
    """
    return json.dumps(json_safe(obj), indent=indent, sort_keys=True, allow_nan=False)


def dumps_strict(obj: Any, *, indent: int | None = 2) -> str:
    """Reject non-finite values outright (no coercion)."""
    assert_finite(obj)
    return json.dumps(obj, indent=indent, sort_keys=True, allow_nan=False)


def finding_for_non_finite(exc: Exception, *, fixture_id: str | None = None) -> Finding:
    return Finding(
        threat_class=ThreatClass.NON_FINITE_JSON.value,
        severity="error",
        message=str(exc),
        fixture_id=fixture_id,
        remediation_owners=list(REMEDIATION_OWNERS[ThreatClass.NON_FINITE_JSON.value]),
    )
