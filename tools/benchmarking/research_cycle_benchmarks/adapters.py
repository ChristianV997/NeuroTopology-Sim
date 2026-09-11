"""Protocol adapters so real research-cycle contracts can be benchmarked later.

The harness ships with deterministic local fixtures/workloads and does NOT import
any other agent's modules. When the real contracts land (ledger, artifact
manifest, evidence graph, cache planner, campaign planner, checkpoint planner),
wrap them in a :class:`TargetSpec` whose ``baseline``/``candidate`` satisfy the
:class:`WorkloadProtocol` below and register them alongside ``TARGETS`` -- no core
change required.
"""
from __future__ import annotations

from typing import Any, Dict, Protocol, runtime_checkable


@runtime_checkable
class WorkloadProtocol(Protocol):
    """A benchmarkable workload: fixture -> result dict with a ``checksum``."""

    def __call__(self, fixture: Dict[str, Any]) -> Dict[str, Any]:
        ...


@runtime_checkable
class FixtureFactory(Protocol):
    """Deterministic fixture factory: ``(seed, size) -> fixture dict``."""

    def __call__(self, seed: int, size: int) -> Dict[str, Any]:
        ...


def adapt_callable(fn: WorkloadProtocol) -> WorkloadProtocol:
    """Identity adapter that documents the required protocol at call sites.

    Kept intentionally trivial: it exists so external contract functions are
    passed through a typed boundary (``WorkloadProtocol``) rather than imported
    into the core, preserving the "no cross-agent import" guarantee.
    """
    return fn
