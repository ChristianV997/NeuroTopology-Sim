"""Evaluation engine for the test admission matrix.

Maps test admission records against detected or simulated platform capabilities,
producing deterministic admission decisions and structured evaluation reports.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence
import yaml

from tools.test_admission.models import (
    ActionWhenUnavailable,
    AdmissionCategory,
    AdmissionDecision,
    AdmissionEvaluation,
    AdmissionMatrixReport,
    DockerPolicy,
    MemoryClass,
    NetworkPolicy,
    PlatformCapabilities,
    ScientificRelevance,
    TestAdmissionRecord,
    TimeoutClass,
    safe_finite_value,
)
from tools.test_admission.probe import probe_platform_capabilities


class AdmissionMatrixEvaluator:
    """Evaluates test admission records against platform capabilities."""

    def __init__(self, capabilities: PlatformCapabilities | None = None):
        self.capabilities = capabilities or probe_platform_capabilities()

    def evaluate_record(self, record: TestAdmissionRecord) -> AdmissionEvaluation:
        """Evaluates a single TestAdmissionRecord, determining the admission decision."""
        # 1. Validation check
        validation_errors = record.validate()
        if validation_errors:
            return AdmissionEvaluation(
                test_group=record.test_group,
                category=record.category.value if isinstance(record.category, AdmissionCategory) else str(record.category),
                decision=AdmissionDecision.INVALID_CONFIGURATION,
                reason=f"Invalid configuration: {'; '.join(validation_errors)}",
                scientific_relevance=record.scientific_relevance.value,
                is_blocked=True,
                diagnostics={"validation_errors": validation_errors},
            )

        cat = record.category
        relevance = record.scientific_relevance.value

        # 2. Check platform capability requirements
        unmet_platform = []
        for req_cap in record.required_platform_capabilities:
            if not self.capabilities.has_capability(req_cap):
                unmet_platform.append(req_cap)

        if unmet_platform:
            # Check if it's an OS incompatibility
            os_caps = {"windows", "posix", "linux", "darwin"}
            if any(c in os_caps for c in unmet_platform):
                return AdmissionEvaluation(
                    test_group=record.test_group,
                    category=cat.value,
                    decision=AdmissionDecision.SKIP_UNSUPPORTED_PLATFORM,
                    reason=f"Test requires platform capability {unmet_platform} not supported on {self.capabilities.os_name}",
                    unmet_platform_capabilities=unmet_platform,
                    scientific_relevance=relevance,
                    is_skipped=True,
                )
            
            # Non-OS unmet platform capability (e.g. symlinks, cuda, external solver)
            if record.action_when_unavailable == ActionWhenUnavailable.SKIP:
                return AdmissionEvaluation(
                    test_group=record.test_group,
                    category=cat.value,
                    decision=AdmissionDecision.SKIP_OPTIONAL_DEPENDENCY,
                    reason=f"Optional platform capability not available: {unmet_platform}",
                    unmet_platform_capabilities=unmet_platform,
                    scientific_relevance=relevance,
                    is_skipped=True,
                )
            else:
                return AdmissionEvaluation(
                    test_group=record.test_group,
                    category=cat.value,
                    decision=AdmissionDecision.BLOCK_MISSING_REQUIRED_DEPENDENCY,
                    reason=f"Required platform capability missing: {unmet_platform}",
                    unmet_platform_capabilities=unmet_platform,
                    scientific_relevance=relevance,
                    is_blocked=True,
                )

        # 3. Check Category-specific constraints
        if cat == AdmissionCategory.WINDOWS_ONLY and not self.capabilities.is_windows:
            return AdmissionEvaluation(
                test_group=record.test_group,
                category=cat.value,
                decision=AdmissionDecision.SKIP_UNSUPPORTED_PLATFORM,
                reason=f"Windows-only test skipped on {self.capabilities.os_name}",
                scientific_relevance=relevance,
                is_skipped=True,
            )

        if cat == AdmissionCategory.POSIX_ONLY and not self.capabilities.is_posix:
            return AdmissionEvaluation(
                test_group=record.test_group,
                category=cat.value,
                decision=AdmissionDecision.SKIP_UNSUPPORTED_PLATFORM,
                reason=f"POSIX-only test skipped on {self.capabilities.os_name}",
                scientific_relevance=relevance,
                is_skipped=True,
            )

        # 4. Check Docker policy
        if record.docker_policy == DockerPolicy.REQUIRED:
            if not self.capabilities.has_docker:
                return AdmissionEvaluation(
                    test_group=record.test_group,
                    category=cat.value,
                    decision=AdmissionDecision.BLOCK_DOCKER_UNAVAILABLE,
                    reason="Docker daemon required by policy but unavailable on host",
                    scientific_relevance=relevance,
                    is_blocked=True,
                )
        elif record.docker_policy == DockerPolicy.OPTIONAL:
            if not self.capabilities.has_docker:
                return AdmissionEvaluation(
                    test_group=record.test_group,
                    category=cat.value,
                    decision=AdmissionDecision.SKIP_OPTIONAL_DEPENDENCY,
                    reason="Optional Docker capability not available on host",
                    scientific_relevance=relevance,
                    is_skipped=True,
                )

        # 5. Check Network policy
        if record.network_policy == NetworkPolicy.REQUIRED:
            return AdmissionEvaluation(
                test_group=record.test_group,
                category=cat.value,
                decision=AdmissionDecision.BLOCK_NETWORK_POLICY,
                reason="Test requires live network access, which violates repository offline policy",
                scientific_relevance=relevance,
                is_blocked=True,
            )

        # 6. Check Cloud / QPU
        if cat == AdmissionCategory.CLOUD_QPU or "cloud_qpu" in record.required_platform_capabilities:
            if not self.capabilities.has_cloud_qpu:
                if record.action_when_unavailable == ActionWhenUnavailable.SKIP:
                    return AdmissionEvaluation(
                        test_group=record.test_group,
                        category=cat.value,
                        decision=AdmissionDecision.SKIP_OPTIONAL_DEPENDENCY,
                        reason="Cloud QPU credentials/endpoints not configured; skipping optional cloud test",
                        scientific_relevance=relevance,
                        is_skipped=True,
                    )
                else:
                    return AdmissionEvaluation(
                        test_group=record.test_group,
                        category=cat.value,
                        decision=AdmissionDecision.BLOCK_CLOUD_UNAVAILABLE,
                        reason="Cloud QPU required but credentials/endpoints not configured",
                        scientific_relevance=relevance,
                        is_blocked=True,
                    )

        # 7. Check Required Packages
        missing_req = []
        for pkg in record.required_packages:
            installed = self.capabilities.installed_packages.get(pkg)
            if installed is None:
                missing_req.append(pkg)

        if missing_req:
            return AdmissionEvaluation(
                test_group=record.test_group,
                category=cat.value,
                decision=AdmissionDecision.BLOCK_MISSING_REQUIRED_DEPENDENCY,
                reason=f"Missing required packages: {missing_req}",
                missing_required_packages=missing_req,
                scientific_relevance=relevance,
                is_blocked=True,
            )

        # 8. Check Optional Packages
        missing_opt = []
        for pkg in record.optional_packages:
            installed = self.capabilities.installed_packages.get(pkg)
            if installed is None:
                missing_opt.append(pkg)

        if missing_opt:
            return AdmissionEvaluation(
                test_group=record.test_group,
                category=cat.value,
                decision=AdmissionDecision.SKIP_OPTIONAL_DEPENDENCY,
                reason=f"Missing optional packages: {missing_opt}",
                missing_optional_packages=missing_opt,
                scientific_relevance=relevance,
                is_skipped=True,
            )

        # 9. All conditions met: RUN
        return AdmissionEvaluation(
            test_group=record.test_group,
            category=cat.value,
            decision=AdmissionDecision.RUN,
            reason="All required dependencies and platform capabilities are satisfied",
            scientific_relevance=relevance,
            is_runnable=True,
        )

    def evaluate_matrix(self, records: Sequence[TestAdmissionRecord]) -> AdmissionMatrixReport:
        """Evaluates an ordered list of TestAdmissionRecord items."""
        evals: list[AdmissionEvaluation] = []
        summary_by_decision: dict[str, int] = {d.value: 0 for d in AdmissionDecision}
        summary_by_category: dict[str, dict[str, int]] = {c.value: {"RUN": 0, "SKIP": 0, "BLOCK": 0} for c in AdmissionCategory}

        runnable_groups = []
        skipped_groups = []
        blocked_groups = []
        invalid_groups = []

        for record in records:
            evaluation = self.evaluate_record(record)
            evals.append(evaluation)

            dec = evaluation.decision.value
            summary_by_decision[dec] = summary_by_decision.get(dec, 0) + 1

            cat_str = evaluation.category
            if cat_str in summary_by_category:
                if evaluation.is_runnable:
                    summary_by_category[cat_str]["RUN"] += 1
                elif evaluation.is_skipped:
                    summary_by_category[cat_str]["SKIP"] += 1
                else:
                    summary_by_category[cat_str]["BLOCK"] += 1

            if evaluation.decision == AdmissionDecision.RUN:
                runnable_groups.append(evaluation.test_group)
            elif evaluation.decision in (AdmissionDecision.SKIP_OPTIONAL_DEPENDENCY, AdmissionDecision.SKIP_UNSUPPORTED_PLATFORM):
                skipped_groups.append(evaluation.test_group)
            elif evaluation.decision == AdmissionDecision.INVALID_CONFIGURATION:
                invalid_groups.append(evaluation.test_group)
            else:
                blocked_groups.append(evaluation.test_group)

        return AdmissionMatrixReport(
            platform=self.capabilities.to_dict(),
            evaluations=evals,
            summary_by_decision=summary_by_decision,
            summary_by_category=summary_by_category,
            runnable_groups=runnable_groups,
            skipped_groups=skipped_groups,
            blocked_groups=blocked_groups,
            invalid_groups=invalid_groups,
        )


def load_admission_records_from_dict(raw_data: Mapping[str, Any]) -> list[TestAdmissionRecord]:
    """Parses a dictionary or YAML structure into a list of TestAdmissionRecord items."""
    records_raw = raw_data.get("admission_records") or raw_data.get("records") or []
    if not isinstance(records_raw, list):
        raise ValueError("admission_records must be a list of records")

    records = []
    for item in records_raw:
        cat_raw = item.get("category", AdmissionCategory.CORE_CPU.value)
        try:
            category = AdmissionCategory(cat_raw)
        except ValueError:
            category = cat_raw  # will be caught during validation

        net_raw = item.get("network_policy", NetworkPolicy.FORBIDDEN.value)
        try:
            net_policy = NetworkPolicy(net_raw)
        except ValueError:
            net_policy = net_raw

        dock_raw = item.get("docker_policy", DockerPolicy.NOT_REQUIRED.value)
        try:
            dock_policy = DockerPolicy(dock_raw)
        except ValueError:
            dock_policy = dock_raw

        mem_raw = item.get("expected_memory_class", MemoryClass.LOW.value)
        try:
            mem_class = MemoryClass(mem_raw)
        except ValueError:
            mem_class = MemoryClass.LOW

        time_raw = item.get("expected_timeout_class", TimeoutClass.SHORT.value)
        try:
            time_class = TimeoutClass(time_raw)
        except ValueError:
            time_class = TimeoutClass.SHORT

        rel_raw = item.get("scientific_relevance", ScientificRelevance.CORE_GATE.value)
        try:
            relevance = ScientificRelevance(rel_raw)
        except ValueError:
            relevance = ScientificRelevance.CORE_GATE

        action_raw = item.get("action_when_unavailable", ActionWhenUnavailable.BLOCK.value)
        try:
            action = ActionWhenUnavailable(action_raw)
        except ValueError:
            action = ActionWhenUnavailable.BLOCK

        rec = TestAdmissionRecord(
            test_group=item.get("test_group", ""),
            category=category,
            required_packages=item.get("required_packages", []),
            optional_packages=item.get("optional_packages", []),
            required_platform_capabilities=item.get("required_platform_capabilities", []),
            network_policy=net_policy,
            docker_policy=dock_policy,
            expected_memory_class=mem_class,
            expected_timeout_class=time_class,
            scientific_relevance=relevance,
            action_when_unavailable=action,
            target_path=item.get("target_path", ""),
            description=item.get("description", ""),
        )
        records.append(rec)

    return records


def load_admission_matrix_file(path: str | Path) -> list[TestAdmissionRecord]:
    """Loads a YAML or JSON admission matrix file."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Admission matrix config file not found: {p}")

    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() in (".yaml", ".yml"):
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)

    return load_admission_records_from_dict(data)
