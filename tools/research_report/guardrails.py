"""Scientific- and status-labeling guardrails shared by every report section.

These helpers exist so a labeling mistake can only happen once, in one
place, instead of being re-implemented (and potentially re-broken) in every
section builder. Each function is defensive: an unrecognized or absent input
degrades to an explicit "unknown" value rather than a guessed one.
"""
from __future__ import annotations

import math
from typing import Any

_KNOWN_PR_STATES = {"open", "merged", "draft", "closed"}
_KNOWN_CI_STATUSES = {"passed", "failed", "pending", "not_started", "skipped"}
_KNOWN_DATA_MODES = {"synthetic", "empirical"}
_KNOWN_TEST_STATUSES = {"passed", "failed", "error", "not_started", "skipped"}

#: The only metric_type value that may ever be rendered using the term
#: "Bayes factor". Everything else (including "proxy_K", "proxy_k", "K",
#: or an absent metric_type) is rendered with an explicit non-Bayes-factor
#: caveat. This is guardrail #3 from docs/research/report_contract.md.
FORMAL_BAYES_FACTOR_METRIC_TYPE = "bayes_factor"


def safe_number(value: Any) -> float | None:
    """Return ``value`` as a finite float, or ``None`` (guardrail #6).

    Handles values that survived JSON parsing as finite-looking literals but
    overflow to +/-inf (e.g. ``1e400``), and rejects bool (which is a bool
    subclass of int but never a meaningful numeric metric here).
    """
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def normalize_pr_state(value: Any) -> str:
    """Pass through only an explicitly-declared PR state (guardrail #1).

    A branch existing, or any other side information, must never be used to
    upgrade a PR's status to "merged" -- only a literal ``state: "merged"``
    in the source record does that.
    """
    if isinstance(value, str) and value in _KNOWN_PR_STATES:
        return value
    return "unknown"


def normalize_ci_status(value: Any) -> str:
    """Pass through only an explicitly-declared CI status (guardrail #2)."""
    if isinstance(value, str) and value in _KNOWN_CI_STATUSES:
        return value
    return "unknown"


def normalize_test_job_status(value: Any) -> str:
    """Pass through only an explicitly-declared test-job status (guardrail #2).

    A job that has not started is never counted as passing.
    """
    if isinstance(value, str) and value in _KNOWN_TEST_STATUSES:
        return value
    return "unknown"


def normalize_data_mode(value: Any) -> str:
    """Pass through only "synthetic" or "empirical" (guardrail #4).

    Anything else -- missing, misspelled, or a different vocabulary --
    becomes "unknown" rather than silently defaulting to either label.
    """
    if isinstance(value, str) and value in _KNOWN_DATA_MODES:
        return value
    return "unknown"


def describe_metric(metric_type: Any, metric_value: Any, unit: Any) -> dict[str, Any]:
    """Build a metric description that can never mislabel a proxy as a Bayes factor.

    Guardrail #3: only ``metric_type == "bayes_factor"`` produces a display
    label containing the phrase "Bayes factor". Every other metric type
    (including the common "proxy_K") is labeled with its literal type plus
    an explicit "(not a formal Bayes factor)" caveat.
    """
    declared_type = metric_type if isinstance(metric_type, str) and metric_type.strip() else "unspecified_metric"
    is_formal_bayes_factor = declared_type == FORMAL_BAYES_FACTOR_METRIC_TYPE
    if is_formal_bayes_factor:
        display_label = "Bayes factor"
    else:
        display_label = f"{declared_type} (not a formal Bayes factor)"
    return {
        "metric_type": declared_type,
        "metric_value": safe_number(metric_value),
        "unit": unit if isinstance(unit, str) and unit.strip() else None,
        "display_label": display_label,
        "is_formal_bayes_factor": is_formal_bayes_factor,
    }
