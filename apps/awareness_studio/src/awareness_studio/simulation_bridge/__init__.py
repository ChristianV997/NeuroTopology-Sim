"""Fail-closed bridge from Awareness Studio to registered local solvers."""

from .bridge import (
    BridgeRequest,
    BridgeResult,
    BridgeState,
    RegisteredWorkload,
    ResourceBudget,
    SimulationBridge,
    WorkloadRegistry,
)

__all__ = [
    "BridgeRequest",
    "BridgeResult",
    "BridgeState",
    "RegisteredWorkload",
    "ResourceBudget",
    "SimulationBridge",
    "WorkloadRegistry",
]
