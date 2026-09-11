"""One deterministic, pure check function per rubric dimension.

Every function takes the whole :class:`~models.ResearchPlan` and
returns exactly one :class:`~models.CriterionResult`. None of these
functions infer a missing value or fill in a method the plan didn't
specify -- an absent field is always reported as missing/blocking, never
guessed at.
"""
from __future__ import annotations

from .models import CriterionResult, EVIDENCE_CLASSES, ResearchPlan, make_result

_OVERCLAIM_PHRASES: tuple[str, ...] = (
    "proves", "proof that", "confirms", "causes", "demonstrates conclusively",
    "establishes that", "is caused by", "definitively shows",
)

_ALLOWED_PAIRING_STRATEGIES = frozenset({"paired", "unpaired", "within_subject", "between_subject"})
_ALLOWED_SPLIT_UNITS = frozenset({"subject", "session", "time"})


def check_falsifiable_question(plan: ResearchPlan) -> CriterionResult:
    if not plan.research_question.strip():
        return make_result("falsifiable_question", "missing", "no research_question was provided")
    if not plan.falsifiability_criteria.strip():
        return make_result(
            "falsifiable_question", "warning",
            "research_question is present but falsifiability_criteria (what result would falsify it) is not stated",
        )
    return make_result("falsifiable_question", "pass", "research question and falsifiability criteria both provided")


def check_primary_endpoint(plan: ResearchPlan) -> CriterionResult:
    if not plan.primary_endpoint.strip():
        return make_result("primary_endpoint", "missing", "no primary_endpoint was provided")
    return make_result("primary_endpoint", "pass", "primary_endpoint is explicit")


def check_alternative_explanations(plan: ResearchPlan) -> CriterionResult:
    if not plan.alternative_explanations:
        return make_result(
            "alternative_explanations", "warning", "no alternative explanations for the hypothesized effect were considered"
        )
    return make_result(
        "alternative_explanations", "pass",
        f"{len(plan.alternative_explanations)} alternative explanation(s) considered",
    )


def check_source_quality_provenance(plan: ResearchPlan) -> CriterionResult:
    if not plan.sources:
        return make_result("source_quality_provenance", "missing", "no sources were provided (missing provenance)")
    without_identifier = [s for s in plan.sources if not s.identifier]
    if without_identifier:
        return make_result(
            "source_quality_provenance", "blocker",
            f"{len(without_identifier)} of {len(plan.sources)} source(s) have no DOI/arXiv-id/URL identifier -- identity cannot be checked",
        )
    disputed = [s for s in plan.sources if s.verification_status == "disputed"]
    if disputed:
        return make_result(
            "source_quality_provenance", "warning",
            f"{len(disputed)} of {len(plan.sources)} source(s) have a disputed identity resolution",
        )
    unverified = [s for s in plan.sources if s.verification_status in (None, "unverified")]
    if unverified:
        return make_result(
            "source_quality_provenance", "warning",
            f"{len(unverified)} of {len(plan.sources)} source(s) have not been independently verified",
        )
    return make_result(
        "source_quality_provenance", "pass", f"all {len(plan.sources)} source(s) carry an identifier and are verified"
    )


def check_dataset_identity_checksum(plan: ResearchPlan) -> CriterionResult:
    if not plan.dataset_id:
        return make_result("dataset_identity_checksum", "missing", "no dataset_id was provided")
    if not plan.dataset_checksum:
        return make_result(
            "dataset_identity_checksum", "blocker",
            f"dataset_id {plan.dataset_id!r} is provided but no dataset_checksum was given",
        )
    return make_result("dataset_identity_checksum", "pass", "dataset identity and checksum both provided")


def check_condition_label_validity(plan: ResearchPlan) -> CriterionResult:
    if not plan.condition_labels:
        return make_result("condition_label_validity", "missing", "no condition_labels were provided")
    undefined = [
        label for label in plan.condition_labels
        if not plan.condition_label_definitions.get(label, "").strip()
    ]
    if undefined:
        return make_result(
            "condition_label_validity", "blocker",
            f"{len(undefined)} condition label(s) have no definition and are ambiguous: {undefined}",
        )
    return make_result(
        "condition_label_validity", "pass", f"all {len(plan.condition_labels)} condition label(s) are defined"
    )


def check_pairing_sample_size_adequacy(plan: ResearchPlan) -> CriterionResult:
    if plan.sample_size is None:
        return make_result("pairing_sample_size_adequacy", "missing", "no sample_size was provided")
    if plan.minimum_required_sample_size is not None and plan.sample_size < plan.minimum_required_sample_size:
        return make_result(
            "pairing_sample_size_adequacy", "blocker",
            f"sample_size={plan.sample_size} is below the plan's own stated "
            f"minimum_required_sample_size={plan.minimum_required_sample_size}",
        )
    if plan.pairing_strategy is None:
        return make_result(
            "pairing_sample_size_adequacy", "warning", "sample_size is provided but no pairing_strategy was stated"
        )
    if plan.pairing_strategy not in _ALLOWED_PAIRING_STRATEGIES:
        return make_result(
            "pairing_sample_size_adequacy", "warning",
            f"pairing_strategy {plan.pairing_strategy!r} is not one of {sorted(_ALLOWED_PAIRING_STRATEGIES)}",
        )
    return make_result(
        "pairing_sample_size_adequacy", "pass",
        f"sample_size={plan.sample_size} meets the plan's stated minimum, with pairing_strategy={plan.pairing_strategy!r}",
    )


def check_power_or_precision_plan(plan: ResearchPlan) -> CriterionResult:
    if plan.power_analysis is None:
        return make_result("power_or_precision_plan", "warning", "no power/precision analysis was provided")
    missing = [
        field_name for field_name in ("method", "target_power", "effect_size", "alpha")
        if getattr(plan.power_analysis, field_name) is None
    ]
    if missing:
        return make_result(
            "power_or_precision_plan", "warning",
            f"power_analysis is present but missing: {missing}",
        )
    return make_result("power_or_precision_plan", "pass", "power/precision plan is fully specified")


def check_multiplicity_correction(plan: ResearchPlan) -> CriterionResult:
    planned_tests = plan.number_of_planned_tests
    if planned_tests is not None and planned_tests > 1:
        if not plan.multiplicity_correction or plan.multiplicity_correction == "none_needed_single_test":
            return make_result(
                "multiplicity_correction", "blocker",
                f"{planned_tests} planned tests were declared but no multiplicity correction method was specified",
            )
        return make_result(
            "multiplicity_correction", "pass",
            f"multiplicity correction {plan.multiplicity_correction!r} specified for {planned_tests} planned tests",
        )
    return make_result(
        "multiplicity_correction", "pass",
        "at most one planned test declared; multiplicity correction not applicable",
    )


def check_null_model_specification(plan: ResearchPlan) -> CriterionResult:
    if plan.null_model is None:
        return make_result("null_model_specification", "missing", "no null_model was provided")
    if not plan.null_model.method or not (plan.null_model.description or "").strip():
        return make_result(
            "null_model_specification", "warning",
            "null_model is present but incomplete (missing method or description)",
        )
    return make_result("null_model_specification", "pass", "null model is fully specified")


def check_leakage_prevention(plan: ResearchPlan) -> CriterionResult:
    if plan.known_leakage_risks and not plan.leakage_controls:
        return make_result(
            "leakage_prevention", "blocker",
            f"{len(plan.known_leakage_risks)} known leakage risk(s) declared with no leakage_controls to address them",
        )
    if not plan.leakage_controls and not plan.known_leakage_risks:
        return make_result(
            "leakage_prevention", "warning", "no leakage controls declared and no leakage risks were assessed"
        )
    return make_result(
        "leakage_prevention", "pass",
        f"{len(plan.leakage_controls)} leakage control(s) declared for {len(plan.known_leakage_risks)} known risk(s)",
    )


def check_split_strategy(plan: ResearchPlan) -> CriterionResult:
    if plan.split_strategy is None:
        return make_result("split_strategy", "missing", "no split_strategy was provided")
    if plan.split_strategy.unit not in _ALLOWED_SPLIT_UNITS or not plan.split_strategy.method:
        return make_result(
            "split_strategy", "warning",
            f"split_strategy is present but incomplete (unit={plan.split_strategy.unit!r}, "
            f"method={plan.split_strategy.method!r})",
        )
    return make_result(
        "split_strategy", "pass",
        f"split by {plan.split_strategy.unit} using method {plan.split_strategy.method!r}",
    )


def check_preprocessing_lock(plan: ResearchPlan) -> CriterionResult:
    if not plan.preprocessing_steps:
        return make_result("preprocessing_lock", "missing", "no preprocessing_steps were provided")
    if plan.preprocessing_locked_before_analysis is not True:
        return make_result(
            "preprocessing_lock", "warning",
            "preprocessing_steps are listed but preprocessing_locked_before_analysis is not confirmed True",
        )
    return make_result(
        "preprocessing_lock", "pass",
        f"{len(plan.preprocessing_steps)} preprocessing step(s) locked before analysis",
    )


def check_measurement_limitations(plan: ResearchPlan) -> CriterionResult:
    if not plan.measurement_limitations:
        return make_result("measurement_limitations", "warning", "no measurement limitations were declared")
    return make_result(
        "measurement_limitations", "pass", f"{len(plan.measurement_limitations)} measurement limitation(s) declared"
    )


def check_compute_resource_budget(plan: ResearchPlan) -> CriterionResult:
    if plan.compute_budget is None or plan.compute_budget.estimated_hours is None:
        return make_result("compute_resource_budget", "warning", "no compute resource budget was provided")
    return make_result(
        "compute_resource_budget", "pass",
        f"estimated_hours={plan.compute_budget.estimated_hours} on hardware={plan.compute_budget.hardware!r}",
    )


def check_reproducibility(plan: ResearchPlan) -> CriterionResult:
    if plan.reproducibility is None:
        return make_result("reproducibility", "missing", "no reproducibility plan was provided")
    missing = [
        name for name in ("seed", "code_version", "environment_pinned")
        if getattr(plan.reproducibility, name) in (None, False)
    ]
    if missing:
        return make_result(
            "reproducibility", "warning", f"reproducibility plan is present but incomplete/unpinned: {missing}"
        )
    return make_result("reproducibility", "pass", "reproducibility plan is fully specified and environment-pinned")


def check_claim_calibration(plan: ResearchPlan) -> CriterionResult:
    if not plan.claim_language.strip():
        return make_result("claim_calibration", "warning", "no claim_language was provided to calibrate")
    lowered = plan.claim_language.lower()
    hit_phrases = [phrase for phrase in _OVERCLAIM_PHRASES if phrase in lowered]
    if hit_phrases and plan.evidence_class_declared in ("synthetic", "proxy"):
        return make_result(
            "claim_calibration", "blocker",
            f"claim_language uses overclaiming/causal phrasing ({hit_phrases}) while "
            f"evidence_class_declared={plan.evidence_class_declared!r}",
        )
    if hit_phrases:
        return make_result(
            "claim_calibration", "warning",
            f"claim_language uses strong causal/confirmatory phrasing ({hit_phrases}); "
            "verify this is warranted by the evidence class and design",
        )
    return make_result("claim_calibration", "pass", "claim_language does not use overclaiming/causal phrasing")


def check_evidence_separation(plan: ResearchPlan) -> CriterionResult:
    if plan.evidence_class_declared is None:
        return make_result(
            "evidence_separation", "missing",
            "evidence_class_declared was not provided (must be one of synthetic/proxy/empirical)",
        )
    if plan.evidence_class_declared not in EVIDENCE_CLASSES:
        return make_result(
            "evidence_separation", "blocker",
            f"evidence_class_declared={plan.evidence_class_declared!r} is not one of {sorted(EVIDENCE_CLASSES)}",
        )
    return make_result(
        "evidence_separation", "pass", f"evidence_class_declared={plan.evidence_class_declared!r} is explicit"
    )


def check_replication_plan(plan: ResearchPlan) -> CriterionResult:
    if not (plan.replication_plan or "").strip():
        return make_result("replication_plan", "warning", "no replication_plan was provided")
    return make_result("replication_plan", "pass", "a replication plan is provided")


def check_ethical_privacy_constraints(plan: ResearchPlan) -> CriterionResult:
    if plan.ethics_privacy is None:
        return make_result("ethical_privacy_constraints", "missing", "no ethics_privacy section was provided")
    if not (plan.ethics_privacy.irb_status or "").strip() or not plan.ethics_privacy.privacy_measures:
        return make_result(
            "ethical_privacy_constraints", "warning",
            f"ethics_privacy is present but incomplete (irb_status={plan.ethics_privacy.irb_status!r}, "
            f"privacy_measures={list(plan.ethics_privacy.privacy_measures)})",
        )
    return make_result(
        "ethical_privacy_constraints", "pass",
        f"irb_status={plan.ethics_privacy.irb_status!r} with {len(plan.ethics_privacy.privacy_measures)} privacy measure(s)",
    )


CHECKS_BY_DIMENSION = {
    "falsifiable_question": check_falsifiable_question,
    "primary_endpoint": check_primary_endpoint,
    "alternative_explanations": check_alternative_explanations,
    "source_quality_provenance": check_source_quality_provenance,
    "dataset_identity_checksum": check_dataset_identity_checksum,
    "condition_label_validity": check_condition_label_validity,
    "pairing_sample_size_adequacy": check_pairing_sample_size_adequacy,
    "power_or_precision_plan": check_power_or_precision_plan,
    "multiplicity_correction": check_multiplicity_correction,
    "null_model_specification": check_null_model_specification,
    "leakage_prevention": check_leakage_prevention,
    "split_strategy": check_split_strategy,
    "preprocessing_lock": check_preprocessing_lock,
    "measurement_limitations": check_measurement_limitations,
    "compute_resource_budget": check_compute_resource_budget,
    "reproducibility": check_reproducibility,
    "claim_calibration": check_claim_calibration,
    "evidence_separation": check_evidence_separation,
    "replication_plan": check_replication_plan,
    "ethical_privacy_constraints": check_ethical_privacy_constraints,
}
