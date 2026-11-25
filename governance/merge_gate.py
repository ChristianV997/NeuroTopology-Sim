"""Deterministic merge-gate policy for NeuroTopology-Sim.

Pure, typed, network-free decision function: given a `MergeGateInput`
snapshot describing a PR's reconciliation/CI/scientific/governance state
(as already gathered by some other, already-existing tool -- e.g. the
read-only reconciliation in `tools/integration_reconciliation` from PR
#218, or any other source able to populate the same fields), `evaluate()`
returns exactly one `MergeGateDecision`.

This module deliberately has ZERO import dependency on
`tools/integration_reconciliation` or any GitHub client: it is the policy
layer, not the data-gathering layer. A caller builds a `MergeGateInput`
from whatever reconciliation data it already has (a `ReconciliationEntry`,
a hand-built dict, a test fixture) and calls `evaluate()` -- this module
never fetches anything itself, and its own test suite needs no snapshot
files, no git fixtures, and no network.

See docs/governance/merge_gate_policy.md for the full rule-by-rule
rationale and the priority order rule ties are resolved by.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, Optional

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

# The eight decisions this policy can return. Kept as a plain frozenset of
# strings (not an Enum) so a caller can serialize a MergeGateDecision with
# bare `dataclasses.asdict`/`json.dumps` and get back exactly these
# literal strings, no enum-name translation needed.
DECISION_STATES: FrozenSet[str] = frozenset({
    "READY_FOR_REVIEW",
    "READY_FOR_MERGE",
    "BLOCKED_BY_DEPENDENCY",
    "BLOCKED_BY_CI",
    "BLOCKED_BY_INFRASTRUCTURE",
    "BLOCKED_BY_SCIENTIFIC_REVIEW",
    "BLOCKED_BY_DUPLICATE_OR_SUPERSEDED_WORK",
    "REJECTED_UNSAFE",
})

# A required check's own state -- deliberately the same four-plus-two
# vocabulary as tools/integration_reconciliation/ci_interpretation.py
# (this module does not import that one, but a caller translating a
# ci_interpretation.CheckClassification into a MergeGateInput should map
# "unknown"/"mixed" through as-is; both are handled below).
CHECK_STATES: FrozenSet[str] = frozenset({
    "passing", "failing", "pending", "not_run",
    "infrastructure_blocked", "billing_blocked", "mixed", "unknown",
})

CHANGED_FILE_CATEGORIES: FrozenSet[str] = frozenset({
    "scientific_model", "signal_adapter", "streaming_tool", "dashboard_route",
    "ci_workflow", "governance", "tests", "docs", "tooling", "other",
})

BAYES_FACTOR_EVIDENCE_KINDS: FrozenSet[str] = frozenset({"proxy", "formal"})


@dataclass(frozen=True)
class MergeGateInput:
    """Everything the policy needs, and nothing it derives on its own.

    Every field defaults to a conservative ("nothing verified yet") value
    so a caller populating only a handful of fields for a test still gets
    deterministic, safe behavior rather than an exception -- this mirrors
    the "Evidence" pattern used elsewhere in this reconciliation effort:
    absence of information is never silently read as success.
    """

    # -- PR / branch identity and lifecycle --
    pr_state: Optional[str] = None            # "open" | "closed" | "merged" | None (unknown)
    draft: Optional[bool] = None
    branch_present: Optional[bool] = None
    pr_present: Optional[bool] = None
    base_ref: Optional[str] = None
    head_ref: Optional[str] = None
    mergeable: Optional[bool] = None           # True="clean", False="dirty/conflicting", None=unknown

    # -- stacked dependencies --
    is_stacked: bool = False
    stack_dependency_resolved: Optional[bool] = None  # meaningless unless is_stacked
    effective_diff_independently_validated: bool = False  # rule 5's escape hatch

    # -- changed-file categorization --
    changed_file_categories: FrozenSet[str] = field(default_factory=frozenset)

    # -- CI --
    required_checks: dict = field(default_factory=dict)  # {check_name: CHECK_STATES member}
    billing_blocked: bool = False
    infrastructure_blocked: bool = False

    # -- scientific gates --
    scientific_review_required: bool = False
    synthetic_data_claims: bool = False
    claims_empirical_pass: bool = False
    bayes_factor_evidence_kind: Optional[str] = None  # "proxy" | "formal" | None
    requires_formal_bayes_factor: bool = False

    # -- safety / process gates --
    dashboard_imports_solver: bool = False
    governance_validated: Optional[bool] = None   # None = not run / unknown
    secret_scan_clean: Optional[bool] = None      # None = not run / unknown

    # -- duplicate / superseded --
    duplicate: bool = False
    superseded: bool = False
    explicit_replacement_decision: bool = False   # a human has picked a winner


@dataclass(frozen=True)
class MergeGateDecision:
    decision: str
    reason_codes: tuple[str, ...]
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "decision": self.decision,
            "reason_codes": list(self.reason_codes),
            "notes": list(self.notes),
        }


def _check_state_to_bool_like(state: Optional[str]) -> str:
    """Normalize an arbitrary/absent check state string to one of
    CHECK_STATES, defaulting anything unrecognized (including None) to
    "not_run" -- rule 1's "an unstarted check is not passing" extends
    naturally: an *unrecognized* check state is treated exactly the same
    as an unstarted one, never as a silent pass."""
    if state in CHECK_STATES:
        return state
    return "not_run"


def _combined_checks(inp: MergeGateInput) -> dict[str, str]:
    """Fold `required_checks` together with the governance/secret-scan
    gates (rule 7) into one uniform check-state mapping, so a single pass
    over this dict implements rules 1, 2, and 7 at once."""
    combined = {name: _check_state_to_bool_like(state) for name, state in inp.required_checks.items()}
    combined["governance"] = (
        "passing" if inp.governance_validated is True
        else "failing" if inp.governance_validated is False
        else "not_run"
    )
    combined["secret_scan"] = (
        "passing" if inp.secret_scan_clean is True
        else "failing" if inp.secret_scan_clean is False
        else "not_run"
    )
    if inp.infrastructure_blocked:
        combined["__infrastructure_blocked_flag__"] = "infrastructure_blocked"
    if inp.billing_blocked:
        combined["__billing_blocked_flag__"] = "billing_blocked"
    return combined


def evaluate(inp: MergeGateInput) -> MergeGateDecision:
    """Deterministic: the same `MergeGateInput` always produces the same
    `MergeGateDecision` -- no clock, no randomness, no I/O. Rules are
    evaluated in a fixed priority order (most severe first) so exactly one
    decision is ever returned; see docs/governance/merge_gate_policy.md
    for the full table."""

    # ---- Tier 0: hard safety rejections (rules 3, 4, 6) ----
    if inp.dashboard_imports_solver:
        return MergeGateDecision(
            "REJECTED_UNSAFE", ("DASHBOARD_IMPORTS_SOLVER",),
            ("A dashboard route imports a scientific solver module; this is rejected outright, never merely reviewed.",),
        )
    if inp.synthetic_data_claims and inp.claims_empirical_pass:
        return MergeGateDecision(
            "REJECTED_UNSAFE", ("SYNTHETIC_EMPIRICAL_PASS_CLAIM",),
            ("Synthetic data cannot support an empirical PASS claim; this PR is rejected, not merely flagged for review.",),
        )
    if inp.requires_formal_bayes_factor and inp.bayes_factor_evidence_kind == "proxy":
        return MergeGateDecision(
            "REJECTED_UNSAFE", ("PROXY_BAYES_FACTOR_FOR_FORMAL_GATE",),
            ("A descriptive/proxy Bayes-factor statistic cannot satisfy a claim gate that requires formal "
             "marginal-likelihood evidence.",),
        )

    # ---- Tier 1: duplicate / superseded work (rule 8) ----
    if (inp.duplicate or inp.superseded) and not inp.explicit_replacement_decision:
        reasons = []
        if inp.duplicate:
            reasons.append("DUPLICATE_WORK_DETECTED")
        if inp.superseded:
            reasons.append("SUPERSEDED_WORK_DETECTED")
        return MergeGateDecision(
            "BLOCKED_BY_DUPLICATE_OR_SUPERSEDED_WORK", tuple(reasons),
            ("A human must make an explicit replacement decision (which branch wins) before this can proceed.",),
        )

    # ---- Tier 2: stacked dependency (rule 5) ----
    if inp.is_stacked and not (inp.stack_dependency_resolved or inp.effective_diff_independently_validated):
        return MergeGateDecision(
            "BLOCKED_BY_DEPENDENCY", ("STACKED_DEPENDENCY_UNRESOLVED",),
            ("This PR is stacked on another branch that is neither merged/ready nor independently validated "
             "against this PR's own effective diff.",),
        )

    # ---- Tier 3: branch/PR existence sanity ----
    if inp.branch_present is False:
        return MergeGateDecision("BLOCKED_BY_DEPENDENCY", ("BRANCH_NOT_PRESENT",),
                                  ("The expected branch does not exist; there is nothing to merge.",))
    if inp.pr_present is False:
        return MergeGateDecision("READY_FOR_REVIEW", ("NO_PR_YET",),
                                  ("The branch exists but no pull request has been opened for it yet.",))

    # ---- Tier 4: scientific review (rule: scientific claims require
    # STRICTER gates than ordinary code changes -- checked ahead of plain
    # CI status so a scientific PR is never waved through as "just a CI
    # matter" when it also needs a human scientific reviewer) ----
    if inp.scientific_review_required:
        return MergeGateDecision(
            "BLOCKED_BY_SCIENTIFIC_REVIEW", ("SCIENTIFIC_REVIEW_REQUIRED",),
            ("This PR touches scientific claims/paths that require a human scientific reviewer before merge, "
             "independent of CI status.",),
        )

    # ---- Tier 5: required-check aggregation (rules 1, 2, 7) ----
    combined = _combined_checks(inp)
    states = set(combined.values())

    if "infrastructure_blocked" in states:
        blockers = tuple(sorted(name for name, state in combined.items() if state == "infrastructure_blocked"))
        return MergeGateDecision(
            "BLOCKED_BY_INFRASTRUCTURE", ("INFRASTRUCTURE_BLOCKED",) + blockers,
            ("An infrastructure condition (not a code defect) is preventing checks from actually running.",),
        )
    if "billing_blocked" in states:
        blockers = tuple(sorted(name for name, state in combined.items() if state == "billing_blocked"))
        return MergeGateDecision(
            "BLOCKED_BY_INFRASTRUCTURE", ("BILLING_BLOCKED",) + blockers,
            ("A billing/quota condition, not a test failure and not a pass, is preventing checks from running.",),
        )
    if "failing" in states:
        failing = tuple(sorted(name for name, state in combined.items() if state == "failing"))
        return MergeGateDecision("BLOCKED_BY_CI", ("CHECK_FAILING",) + failing, ())

    checks_incomplete = states - {"passing"}  # anything left is pending/not_run/mixed/unknown

    # ---- Tier 6: draft / conflict / completeness / final assembly ----
    if inp.draft:
        return MergeGateDecision("READY_FOR_REVIEW", ("DRAFT",), ())

    if inp.mergeable is False:
        return MergeGateDecision("BLOCKED_BY_CI", ("MERGE_CONFLICT",),
                                  ("The PR has a real merge conflict against its base; this is reported under "
                                   "BLOCKED_BY_CI for lack of a more specific decision state.",))

    if checks_incomplete:
        # Rule 1: an unstarted (or otherwise non-passing-but-not-failing)
        # check means "not passing" -- this can never be READY_FOR_MERGE,
        # but it is not a hard block either; it's simply not finished yet.
        return MergeGateDecision(
            "READY_FOR_REVIEW", ("CHECKS_INCOMPLETE",) + tuple(sorted(
                name for name, state in combined.items() if state != "passing"
            )),
            (),
        )

    return MergeGateDecision("READY_FOR_MERGE", ("ALL_GATES_PASSED",), ())
