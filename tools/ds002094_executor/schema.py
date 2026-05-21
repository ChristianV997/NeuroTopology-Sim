from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass
class DS002094DatasetRegistry: data: dict[str, Any]
@dataclass
class DS002094LocalDataPreflight: data: dict[str, Any]
@dataclass
class DS002094ContractRequirement: data: dict[str, Any]
@dataclass
class DS002094ReaderPreflight: data: dict[str, Any]
@dataclass
class DS002094MNEAdapterPlan: data: dict[str, Any]
@dataclass
class DS002094LevelMAdapterPlan: data: dict[str, Any]
@dataclass
class DS002094LevelTAdapterPlan: data: dict[str, Any]
@dataclass
class DS002094ArtifactPlan: data: dict[str, Any]
@dataclass
class DS002094RealExecutionGate: data: dict[str, Any]
@dataclass
class DS002094PostExecutionControlsInterface: data: dict[str, Any]
@dataclass
class DS002094ReadinessReport: data: dict[str, Any]
@dataclass
class DS002094ValidationResult: data: dict[str, Any]
