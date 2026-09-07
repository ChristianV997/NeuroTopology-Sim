"""Data models and enums for test admission and capability gating.

Defines the typed admission matrix schema, allowed decisions, and evaluation results
in accordance with NeuroTopology-Sim CI isolation rules.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import math
from typing import Any, Sequence


class AdmissionDecision(str, Enum):
    """Allowed test admission decisions."""
    RUN = "RUN"
    SKIP_OPTIONAL_DEPENDENCY = "SKIP_OPTIONAL_DEPENDENCY"
    SKIP_UNSUPPORTED_PLATFORM = "SKIP_UNSUPPORTED_PLATFORM"
    BLOCK_MISSING_REQUIRED_DEPENDENCY = "BLOCK_MISSING_REQUIRED_DEPENDENCY"
    BLOCK_NETWORK_POLICY = "BLOCK_NETWORK_POLICY"
    BLOCK_DOCKER_UNAVAILABLE = "BLOCK_DOCKER_UNAVAILABLE"
    BLOCK_CLOUD_UNAVAILABLE = "BLOCK_CLOUD_UNAVAILABLE"
    INVALID_CONFIGURATION = "INVALID_CONFIGURATION"


class AdmissionCategory(str, Enum):
    """Standardized test admission categories."""
    CORE_CPU = "core CPU"
    MNE_EEG = "MNE/EEG"
    TDA = "TDA"
    GPU = "GPU"
    DOCKER = "Docker"
    CLOUD_QPU = "cloud/QPU"
    WINDOWS_ONLY = "Windows-only"
    POSIX_ONLY = "POSIX-only"
    OPTIONAL_EXTERNAL_SOLVER = "optional external solver"


class NetworkPolicy(str, Enum):
    """Network admission policies."""
    FORBIDDEN = "forbidden"
    OFFLINE = "offline"
    OPTIONAL = "optional"
    REQUIRED = "required"


class DockerPolicy(str, Enum):
    """Docker daemon requirement policies."""
    FORBIDDEN = "forbidden"
    NOT_REQUIRED = "not_required"
    OPTIONAL = "optional"
    REQUIRED = "required"


class MemoryClass(str, Enum):
    """Expected memory consumption tier."""
    LOW = "low"          # < 1 GB
    MEDIUM = "medium"    # 1 - 4 GB
    HIGH = "high"        # 4 - 16 GB
    EXTREME = "extreme"  # > 16 GB


class TimeoutClass(str, Enum):
    """Expected timeout classification."""
    SHORT = "short"        # < 30s
    MEDIUM = "medium"      # 30s - 120s
    LONG = "long"          # 120s - 300s
    EXTENDED = "extended"  # > 300s


class ScientificRelevance(str, Enum):
    """Scientific relevance and reproducibility gate category."""
    CORE_GATE = "core_gate"
    EMPIRICAL_VALIDATION = "empirical_validation"
    EXPLORATORY = "exploratory"
    HARDWARE_ACCELERATION = "hardware_acceleration"
    REFERENCE_BENCHMARK = "reference_benchmark"


class ActionWhenUnavailable(str, Enum):
    """Action taken when required or optional prerequisites are not met."""
    SKIP = "skip"
    BLOCK = "block"


KNOWN_PLATFORM_CAPABILITIES = frozenset({
    "windows",
    "posix",
    "linux",
    "darwin",
    "symlinks",
    "docker",
    "cuda",
    "gpu",
    "cloud_qpu",
    "external_solver",
})


def safe_finite_value(val: Any) -> Any:
    """Recursively converts non-finite floats to None for strict JSON compliance."""
    if isinstance(val, float):
        return val if math.isfinite(val) else None
    if isinstance(val, (int, str, bool)) or val is None:
        return val
    if isinstance(val, Enum):
        return val.value
    if isinstance(val, dict):
        return {str(k): safe_finite_value(v) for k, v in val.items()}
    if isinstance(val, (list, tuple, set)):
        return [safe_finite_value(v) for v in val]
    return str(val)


@dataclass
class PlatformCapabilities:
    """Detected or simulated platform capabilities."""
    os_name: str
    is_windows: bool
    is_posix: bool
    is_linux: bool
    is_darwin: bool
    has_symlinks: bool
    has_docker: bool
    has_cuda: bool
    has_gpu: bool
    has_cloud_qpu: bool
    has_external_solver: bool
    installed_packages: dict[str, str | None] = field(default_factory=dict)
    network_available: bool = False
    cpu_cores: int | None = None
    total_memory_gb: float | None = None

    def has_capability(self, capability: str) -> bool:
        cap = capability.lower().strip()
        if cap == "windows":
            return self.is_windows
        if cap == "posix":
            return self.is_posix
        if cap == "linux":
            return self.is_linux
        if cap == "darwin":
            return self.is_darwin
        if cap == "symlinks":
            return self.has_symlinks
        if cap == "docker":
            return self.has_docker
        if cap in ("cuda", "gpu"):
            return self.has_cuda or self.has_gpu
        if cap in ("cloud_qpu", "qpu"):
            return self.has_cloud_qpu
        if cap in ("external_solver", "solver"):
            return self.has_external_solver
        return False

    def to_dict(self) -> dict[str, Any]:
        return safe_finite_value(asdict(self))


@dataclass
class TestAdmissionRecord:
    """Specification of requirements and constraints for a test group or command."""
    __test__ = False  # Instruct pytest not to collect this as a test class
    test_group: str
    category: AdmissionCategory
    required_packages: list[str] = field(default_factory=list)
    optional_packages: list[str] = field(default_factory=list)
    required_platform_capabilities: list[str] = field(default_factory=list)
    network_policy: NetworkPolicy = NetworkPolicy.FORBIDDEN
    docker_policy: DockerPolicy = DockerPolicy.NOT_REQUIRED
    expected_memory_class: MemoryClass = MemoryClass.LOW
    expected_timeout_class: TimeoutClass = TimeoutClass.SHORT
    scientific_relevance: ScientificRelevance = ScientificRelevance.CORE_GATE
    action_when_unavailable: ActionWhenUnavailable = ActionWhenUnavailable.BLOCK
    target_path: str = ""
    description: str = ""

    def validate(self) -> list[str]:
        """Validates internal consistency of the admission record."""
        errors = []
        if not self.test_group or not self.test_group.strip():
            errors.append("test_group cannot be empty")
        
        # Validate known category
        if not isinstance(self.category, AdmissionCategory):
            try:
                AdmissionCategory(self.category)
            except ValueError:
                errors.append(f"Unknown admission category: {self.category}")

        # Validate platform capabilities against known vocabulary
        for cap in self.required_platform_capabilities:
            if cap.lower().strip() not in KNOWN_PLATFORM_CAPABILITIES:
                errors.append(f"Unknown platform capability requirement: '{cap}'")

        # Validate policies
        if not isinstance(self.network_policy, NetworkPolicy):
            try:
                NetworkPolicy(self.network_policy)
            except ValueError:
                errors.append(f"Invalid network_policy: {self.network_policy}")

        if not isinstance(self.docker_policy, DockerPolicy):
            try:
                DockerPolicy(self.docker_policy)
            except ValueError:
                errors.append(f"Invalid docker_policy: {self.docker_policy}")

        return errors

    def to_dict(self) -> dict[str, Any]:
        return safe_finite_value(asdict(self))


@dataclass
class AdmissionEvaluation:
    """Evaluation result for a single test admission record."""
    test_group: str
    category: str
    decision: AdmissionDecision
    reason: str
    missing_required_packages: list[str] = field(default_factory=list)
    missing_optional_packages: list[str] = field(default_factory=list)
    unmet_platform_capabilities: list[str] = field(default_factory=list)
    scientific_relevance: str = ""
    is_runnable: bool = False
    is_skipped: bool = False
    is_blocked: bool = False
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return safe_finite_value(asdict(self))


@dataclass
class AdmissionMatrixReport:
    """Structured report of admission evaluations across test groups."""
    schema: str = "NeuroTopologySim.TestAdmissionMatrix.v1"
    platform: dict[str, Any] = field(default_factory=dict)
    evaluations: list[AdmissionEvaluation] = field(default_factory=list)
    summary_by_decision: dict[str, int] = field(default_factory=dict)
    summary_by_category: dict[str, dict[str, int]] = field(default_factory=dict)
    runnable_groups: list[str] = field(default_factory=list)
    skipped_groups: list[str] = field(default_factory=list)
    blocked_groups: list[str] = field(default_factory=list)
    invalid_groups: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return safe_finite_value(asdict(self))
