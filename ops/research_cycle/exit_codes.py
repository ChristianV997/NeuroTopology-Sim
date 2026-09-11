"""Exit-code contract for the research-cycle operator pack.

0  PASS
10 INCOMPLETE
20 BLOCKED
30 FAILURE
40 NOT_AVAILABLE
"""

from __future__ import annotations

from typing import Iterable

PASS = 0
INCOMPLETE = 10
BLOCKED = 20
FAILURE = 30
NOT_AVAILABLE = 40

STATUS_TO_CODE: dict[str, int] = {
    "PASS": PASS,
    "INCOMPLETE": INCOMPLETE,
    "BLOCKED": BLOCKED,
    "FAILURE": FAILURE,
    "NOT_AVAILABLE": NOT_AVAILABLE,
}

CODE_TO_STATUS: dict[int, str] = {code: status for status, code in STATUS_TO_CODE.items()}

# Worst-first aggregation. Missing commands never collapse to PASS.
_RANK = {
    "FAILURE": 50,
    "BLOCKED": 40,
    "NOT_AVAILABLE": 30,
    "INCOMPLETE": 20,
    "PASS": 10,
}


def normalize_status(status: str) -> str:
    token = str(status or "").strip().upper()
    if token in STATUS_TO_CODE:
        return token
    return "FAILURE"


def status_to_exit(status: str) -> int:
    return STATUS_TO_CODE[normalize_status(status)]


def aggregate_statuses(statuses: Iterable[str]) -> str:
    worst = "PASS"
    worst_rank = _RANK[worst]
    for raw in statuses:
        status = normalize_status(raw)
        rank = _RANK[status]
        if rank > worst_rank:
            worst = status
            worst_rank = rank
    return worst
