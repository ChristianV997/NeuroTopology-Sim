"""Orchestrator v0.1 — 9-stage dry-run pipeline.

All outputs are deterministic in dry-run mode.
No network or LLM calls required for dry_run=True.

Output layout per run:
  outputs/orchestrator/<run_id>/
    events.jsonl
    EvidenceLogDraft.md
    Report.md
    GraphUpdate.json
    OpsQueueItem.json
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .event_log import EventLog
from .event_model import EventEnvelope, PIPELINE_STAGES
from awareness_studio.research_cycle import (
    Claim,
    EvidenceClass,
    EvidenceRecord,
    ExperimentSpec as LedgerExperimentSpec,
    Hypothesis as LedgerHypothesis,
    ResearchCycleLedger,
    SourceSnapshot,
    sha256_json,
    stable_id,
)

logger = logging.getLogger(__name__)


# ── Evidence-state gate ───────────────────────────────────────────────────────
#
# Every artifact this orchestrator sees starts as non-evidence. An artifact is
# evidence-ready only when it is declared ENGINEERING or EMPIRICAL AND carries
# source, input, execution, and artifact-lineage identity. Mock, synthetic,
# proxy, planning, failed, partial, blocked, and malformed outputs are classified
# explicitly and never admitted to a claim-bearing or release store.
#
# This gate reads already-produced artifacts. It invokes no solver, makes no
# network call, and never converts a missing value into zero.


class EvidenceState(str, Enum):
    """Explicit evidence states. Only ENGINEERING and EMPIRICAL can be evidence-ready."""

    MOCK = "mock"                        # mock or stub substitute output
    SYNTHETIC = "synthetic"              # synthetic demonstration data
    PROXY = "proxy"                      # proxy inference; never formal or empirical
    ENGINEERING = "engineering"          # software or interface verification
    EMPIRICAL = "empirical"              # measurement on declared, identified inputs
    PLANNING = "planning"                # dry-run planning output
    REVIEW_REQUIRED = "review_required"  # awaiting human review; never evidence
    INVALID = "invalid"                  # malformed, conflicting, or unsupported; rejected
    INCOMPLETE = "incomplete"            # identity or lineage missing, or a partial run
    FAILED = "failed"                    # execution failed
    BLOCKED = "blocked"                  # not authorized, not implemented, or not executed


EVIDENCE_READY_STATES: frozenset = frozenset({EvidenceState.ENGINEERING, EvidenceState.EMPIRICAL})
DRY_RUN_STATES: frozenset = frozenset({EvidenceState.PLANNING, EvidenceState.REVIEW_REQUIRED})
_NON_EVIDENCE_MARKERS: frozenset = frozenset(
    {EvidenceState.MOCK, EvidenceState.SYNTHETIC, EvidenceState.PROXY, EvidenceState.PLANNING}
)
# Run-status vocabulary. Every declared status is matched against these fixed sets.
# A status in none of them is unrecognized and fails closed to INCOMPLETE, so an
# unlisted or misspelled status can never pass by omission. Verdict words (PASS,
# FAIL) are not run-completion statuses: sim/run_cards.py derives them from a metric
# threshold, so PASS is unrecognized here and FAIL counts as a failed run.
_COMPLETED_RUN_STATUSES: frozenset = frozenset({
    "COMPLETED", "COMPLETE", "SUCCESS", "OK", "ENGINEERING_EXECUTION_COMPLETE",
})
_FAILED_RUN_STATUSES: frozenset = frozenset({
    "FAILED", "FAIL", "FAILURE", "ERROR", "ERRORED", "INFRASTRUCTURE_FAILURE",
    "SUCCESS_WITH_ERRORS", "ABORTED", "CANCELLED", "CANCELED", "KILLED", "CRASHED",
})
_INCOMPLETE_RUN_STATUSES: frozenset = frozenset({
    "PARTIAL", "TIMEOUT", "TIMED_OUT", "NOT_RUN", "INCOMPLETE", "INCONCLUSIVE", "RUNNING", "IN_PROGRESS",
})
_BLOCKED_RUN_STATUSES: frozenset = frozenset({"BLOCKED", "NOT_IMPLEMENTED"})
_PLANNING_RUN_STATUSES: frozenset = frozenset({"PLANNING", "PLANNING_ONLY", "PLANNED", "PENDING"})
_REVIEW_RUN_STATUSES: frozenset = frozenset({"REVIEW_REQUIRED", "EVIDENCE_READY_FOR_REVIEW"})
_STATUS_KEYS: Tuple[str, ...] = ("status", "execution_state", "state")
# Precedence when declared statuses disagree: the most severe category wins.
_RUN_STATUS_PRECEDENCE: Tuple[Tuple[str, EvidenceState], ...] = (
    ("failed", EvidenceState.FAILED),
    ("incomplete", EvidenceState.INCOMPLETE),
    ("unrecognized", EvidenceState.INCOMPLETE),
    ("blocked", EvidenceState.BLOCKED),
    ("planning", EvidenceState.PLANNING),
    ("review", EvidenceState.REVIEW_REQUIRED),
)

_DATA_MODE_STATES: Dict[str, EvidenceState] = {
    "mock": EvidenceState.MOCK,
    "mock_only": EvidenceState.MOCK,
    "synthetic": EvidenceState.SYNTHETIC,
    "synthetic_demo": EvidenceState.SYNTHETIC,
    "synthetic_demo_only": EvidenceState.SYNTHETIC,
    "synthetic_fixture": EvidenceState.SYNTHETIC,
    "synthetic_only": EvidenceState.SYNTHETIC,
    "proxy": EvidenceState.PROXY,
    "proxy_inference": EvidenceState.PROXY,
    "proxy_only": EvidenceState.PROXY,
    "planning": EvidenceState.PLANNING,
    "planned": EvidenceState.PLANNING,
    "planning_only": EvidenceState.PLANNING,
    "plan": EvidenceState.PLANNING,
}
# Data modes that describe real measurement or engineering inputs. Any data_mode
# outside this set and outside _DATA_MODE_STATES is unknown and fails closed.
_EVIDENCE_DATA_MODES: frozenset = frozenset({"empirical", "measured", "engineering", "benchmark", "real"})

# Declared evidence-class strings. Values mirror research_cycle.EvidenceClass so
# the two vocabularies cannot drift apart silently.
_DECLARED_CLASS_STATES: Dict[str, EvidenceState] = {
    EvidenceClass.ENGINEERING_FACT.value: EvidenceState.ENGINEERING,
    "engineering": EvidenceState.ENGINEERING,
    "engineering_execution": EvidenceState.ENGINEERING,
    EvidenceClass.BENCHMARK_RESULT.value: EvidenceState.EMPIRICAL,
    EvidenceClass.DESCRIPTIVE_EMPIRICAL.value: EvidenceState.EMPIRICAL,
    "empirical": EvidenceState.EMPIRICAL,
    EvidenceClass.SYNTHETIC_DEMONSTRATION.value: EvidenceState.SYNTHETIC,
    "synthetic_demo_only": EvidenceState.SYNTHETIC,
    EvidenceClass.PROXY_INFERENCE.value: EvidenceState.PROXY,
    "proxy": EvidenceState.PROXY,
    "mock": EvidenceState.MOCK,
    "planning": EvidenceState.PLANNING,
    EvidenceClass.HYPOTHESIS.value: EvidenceState.REVIEW_REQUIRED,
    EvidenceClass.SPECULATION.value: EvidenceState.REVIEW_REQUIRED,
    EvidenceClass.UNSUPPORTED_CLAIM.value: EvidenceState.INVALID,
}
_UNSUPPORTED_DECLARED_CLASSES: Dict[str, str] = {
    EvidenceClass.FORMAL_STATISTICAL_EVIDENCE.value: (
        "formal statistical evidence requires an independently verified formal_bayes_factor, "
        "which this orchestrator keeps null"
    ),
}

# Banned claim language for any claim submitted for evidence. Deliberately
# local: awareness_studio does not import the sciencer_d guardrail package.
_UNSUPPORTED_CLAIM_TERMS: Tuple[str, ...] = (
    "clinical", "diagnos", "treatment", "biomarker", "consciousness detection",
    "detects consciousness", "spiritual attainment", "meditation stage",
    "causal", "causation", "mechanistic", "proves", "proven",
)

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
# Run ids are echoed into summaries and the ledger, so they must be plain identifiers.
# This keeps free text, including a metric value, out of those stores.
_RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_MAX_ARTIFACT_DEPTH = 64


@dataclass(frozen=True)
class EvidenceDecision:
    """Outcome of classifying one artifact or claim. Never grants a scientific pass."""

    state: EvidenceState
    reasons: Tuple[str, ...] = ()
    missing_identities: Tuple[str, ...] = ()

    @property
    def evidence_ready(self) -> bool:
        return self.state in EVIDENCE_READY_STATES and not self.missing_identities

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_state": self.state.value,
            "evidence_ready": self.evidence_ready,
            "reasons": list(self.reasons),
            "missing_identities": list(self.missing_identities),
            "scientific_pass": False,
            "formal_bayes_factor": None,
        }


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256_RE.fullmatch(value))


def _is_plain_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _structural_fault(value: Any, depth: int = 0) -> Optional[str]:
    """Return a fixed code for the first non-finite, non-JSON, non-string-key, or over-deep value.

    The codes deliberately omit the offending text. Artifact keys and values are
    untrusted, and a code that echoed them could carry a metric into the ledger."""
    if depth > _MAX_ARTIFACT_DEPTH:
        return "nesting_too_deep"
    if value is None or isinstance(value, (bool, str, int)):
        return None
    if isinstance(value, float):
        return None if math.isfinite(value) else "non_finite_value"
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                return "non_string_key"
            fault = _structural_fault(item, depth + 1)
            if fault:
                return fault
        return None
    if isinstance(value, (list, tuple)):
        for item in value:
            fault = _structural_fault(item, depth + 1)
            if fault:
                return fault
        return None
    return "unsupported_value_type"


def _identity_gaps(artifact: Mapping) -> Tuple[str, ...]:
    """Identity contract an artifact must satisfy before it can be evidence-ready.

    These blocks are shape-checked and self-declared. Nothing here recomputes a digest
    from artifact bytes, so a well-formed block is not proof that the bytes match."""
    gaps = []
    source = artifact.get("source_identity")
    if not (isinstance(source, Mapping) and _is_nonempty_str(source.get("uri")) and _is_sha256(source.get("sha256"))):
        gaps.append("source_identity")
    input_identity = artifact.get("input_identity")
    if not (isinstance(input_identity, Mapping) and _is_sha256(input_identity.get("sha256"))):
        gaps.append("input_identity")
    execution = artifact.get("execution_identity")
    if not (isinstance(execution, Mapping)
            and execution.get("run_id") == artifact.get("run_id")
            and _is_nonempty_str(execution.get("code_commit"))
            and _is_plain_int(execution.get("seed"))
            and _is_sha256(execution.get("command_identity"))):
        gaps.append("execution_identity")
    lineage = artifact.get("artifact_lineage")
    if not (isinstance(lineage, Mapping)
            and lineage.get("status") == "COMPLETE"
            and _is_sha256(lineage.get("artifact_sha256"))):
        gaps.append("artifact_lineage")
    return tuple(gaps)


def _run_status_category(token: str) -> Optional[str]:
    """Category of one declared status token, or None when it is outside the vocabulary."""
    if token in _COMPLETED_RUN_STATUSES:
        return "completed"
    if token in _FAILED_RUN_STATUSES:
        return "failed"
    if token in _INCOMPLETE_RUN_STATUSES:
        return "incomplete"
    if token in _BLOCKED_RUN_STATUSES:
        return "blocked"
    if token in _PLANNING_RUN_STATUSES:
        return "planning"
    if token in _REVIEW_RUN_STATUSES:
        return "review"
    return None


def _classify(artifact: Any) -> EvidenceDecision:
    if not isinstance(artifact, Mapping):
        return EvidenceDecision(EvidenceState.INVALID, ("malformed_artifact:not_an_object",))
    fault = _structural_fault(artifact)
    if fault:
        return EvidenceDecision(EvidenceState.INVALID, (f"malformed_artifact:{fault}",))
    run_id = artifact.get("run_id")
    if run_id is None:
        return EvidenceDecision(EvidenceState.INVALID, ("malformed_artifact:run_id_missing",))
    if not (isinstance(run_id, str) and _RUN_ID_RE.fullmatch(run_id)):
        return EvidenceDecision(EvidenceState.INVALID, ("malformed_artifact:run_id_invalid",))

    # Assertions the orchestrator itself keeps fixed. An input that asserts a pass or a
    # formal statistic is rejected, not trusted.
    for assertion in ("scientific_pass", "scientific_evidence"):
        if assertion in artifact and artifact[assertion] is not False:
            return EvidenceDecision(EvidenceState.INVALID, (f"unsupported_claim:{assertion}_asserted",))
    if artifact.get("formal_bayes_factor") is not None:
        return EvidenceDecision(EvidenceState.INVALID, ("unsupported_claim:formal_bayes_factor_must_be_null",))

    markers: set = set()
    for flag in ("mock", "synthetic"):
        if flag in artifact and not isinstance(artifact[flag], bool):
            return EvidenceDecision(EvidenceState.INVALID, ("malformed_artifact:flag_not_boolean",))
    if artifact.get("mock") is True:
        markers.add(EvidenceState.MOCK)
    if artifact.get("synthetic") is True:
        markers.add(EvidenceState.SYNTHETIC)

    data_mode = artifact.get("data_mode")
    if data_mode is not None:
        if not _is_nonempty_str(data_mode):
            return EvidenceDecision(EvidenceState.INVALID, ("malformed_artifact:data_mode_invalid",))
        mode = data_mode.strip().lower()
        mapped = _DATA_MODE_STATES.get(mode)
        if mapped is not None:
            markers.add(mapped)
        elif mode not in _EVIDENCE_DATA_MODES:
            return EvidenceDecision(EvidenceState.INVALID, ("malformed_artifact:unknown_data_mode",))

    declared_state: Optional[EvidenceState] = None
    declared_raw = artifact.get("evidence_class")
    if declared_raw is not None:
        if not _is_nonempty_str(declared_raw):
            return EvidenceDecision(EvidenceState.INVALID, ("malformed_artifact:evidence_class_invalid",))
        key = declared_raw.strip().lower()
        if key in _UNSUPPORTED_DECLARED_CLASSES:
            return EvidenceDecision(
                EvidenceState.INVALID, (f"unsupported_claim:{key}: {_UNSUPPORTED_DECLARED_CLASSES[key]}",)
            )
        declared_state = _DECLARED_CLASS_STATES.get(key)
        if declared_state is None:
            return EvidenceDecision(EvidenceState.INVALID, ("unknown_evidence_class",))

    if len(markers) > 1:
        names = ",".join(sorted(marker.value for marker in markers))
        return EvidenceDecision(EvidenceState.INVALID, (f"conflicting_non_evidence_markers:{names}",))

    reasons: list = []
    if markers:
        state = next(iter(markers))
        if declared_state in EVIDENCE_READY_STATES or (
            declared_state in _NON_EVIDENCE_MARKERS and declared_state is not state
        ):
            detail = declared_state.value if declared_state else "undeclared"
            return EvidenceDecision(
                EvidenceState.INVALID,
                (f"conflicting_evidence_declaration:{state.value} data declared {detail}",),
            )
    elif declared_state is None:
        return EvidenceDecision(EvidenceState.INCOMPLETE, ("evidence_class_undeclared",))
    else:
        state = declared_state

    # Every present status key is checked, so a FAILED execution_state cannot be
    # overridden by a COMPLETED status, and a null status is never read as absent.
    categories: set = set()
    for key in _STATUS_KEYS:
        if key not in artifact:
            continue
        raw = artifact[key]
        if not _is_nonempty_str(raw):
            return EvidenceDecision(EvidenceState.INVALID, ("malformed_artifact:status_not_text",))
        token = raw.strip().upper()
        category = _run_status_category(token)
        if category is None:
            categories.add("unrecognized")
            reasons.append("run_status:unrecognized")
        else:
            categories.add(category)
            reasons.append(f"run_status:{token}")

    if state not in _NON_EVIDENCE_MARKERS and state is not EvidenceState.INVALID:
        for category, mapped_state in _RUN_STATUS_PRECEDENCE:
            if category in categories:
                state = mapped_state
                break

    if state in EVIDENCE_READY_STATES:
        if not categories:
            return EvidenceDecision(EvidenceState.INCOMPLETE, ("run_status_undeclared",))
        gaps = _identity_gaps(artifact)
        if gaps:
            return EvidenceDecision(
                EvidenceState.INCOMPLETE,
                tuple(reasons) + (f"identity_incomplete:{','.join(gaps)}",),
                gaps,
            )
    return EvidenceDecision(state, tuple(reasons))


def classify_artifact(artifact: Any) -> EvidenceDecision:
    """Classify one already-produced artifact. Fails closed on any ambiguity.

    An unexpected error during classification is itself a rejection, never a pass."""
    try:
        return _classify(artifact)
    except (TypeError, ValueError, OverflowError, RecursionError):
        return EvidenceDecision(EvidenceState.INVALID, ("malformed_artifact:unexpected_value",))


def normalize_metric(value: Any) -> Optional[float]:
    """Finite numbers pass through; missing, boolean, non-numeric, and non-finite values stay null."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            number = float(value)
        except OverflowError:
            return None  # an integer too large for a float is not a usable measurement
        return number if math.isfinite(number) else None
    return None


def admit_metrics(decision: EvidenceDecision, metrics: Any) -> Optional[Dict[str, Optional[float]]]:
    """Admit metrics only for an evidence-ready decision. Otherwise return None."""
    if not decision.evidence_ready or not isinstance(metrics, Mapping):
        return None
    return {str(key): normalize_metric(value) for key, value in metrics.items()}


def assess_claim(claim: Any) -> EvidenceDecision:
    """Gate a claim before it can be written into a claim-bearing store."""
    if not isinstance(claim, Mapping):
        return EvidenceDecision(EvidenceState.INVALID, ("malformed_claim:not_an_object",))
    statement = claim.get("statement")
    if not _is_nonempty_str(statement):
        return EvidenceDecision(EvidenceState.INVALID, ("malformed_claim:statement_missing",))
    lowered = statement.lower()
    hits = sorted(term for term in _UNSUPPORTED_CLAIM_TERMS if term in lowered)
    if hits:
        return EvidenceDecision(EvidenceState.INVALID, (f"unsupported_claim:banned_language:{','.join(hits)}",))
    if claim.get("formal_bayes_factor") is not None:
        return EvidenceDecision(EvidenceState.INVALID, ("unsupported_claim:formal_bayes_factor_must_be_null",))
    try:
        requested = EvidenceState(str(claim.get("requested_state", "")).strip().lower())
    except ValueError:
        return EvidenceDecision(EvidenceState.INVALID, ("malformed_claim:requested_state_unknown",))
    if requested not in EVIDENCE_READY_STATES:
        return EvidenceDecision(EvidenceState.REVIEW_REQUIRED, ("proposal_only_not_evidence",))
    evidence = claim.get("evidence") or []
    if not isinstance(evidence, (list, tuple)) or not evidence:
        return EvidenceDecision(EvidenceState.INVALID, ("unsupported_claim:no_evidence_for_requested_state",))
    decisions = [classify_artifact(item) for item in evidence]
    mismatched = sorted({d.state.value for d in decisions if not d.evidence_ready or d.state is not requested})
    if mismatched:
        return EvidenceDecision(
            EvidenceState.INVALID,
            (f"unsupported_claim:evidence_not_ready_for:{requested.value}:{','.join(mismatched)}",),
        )
    return EvidenceDecision(requested)


def _run_evidence_state(dry_run: bool, any_stage_failed: bool) -> EvidenceState:
    """Dry runs emit planning or review states only. Live runs are blocked: no solver exists here."""
    if not dry_run:
        return EvidenceState.BLOCKED
    return EvidenceState.REVIEW_REQUIRED if any_stage_failed else EvidenceState.PLANNING


def _format_metrics(metrics: Any) -> str:
    if not isinstance(metrics, Mapping):
        return "withheld (no evidence-ready artifact)"
    return "; ".join(f"{key}={'null' if value is None else value}" for key, value in metrics.items())


# Per-stage evidence state in a dry run. Live runs are BLOCKED at every stage:
# no solver is implemented, so no stage can produce evidence.
_STAGE_DRY_RUN_STATE: Dict[str, EvidenceState] = {
    "ingest_inputs": EvidenceState.REVIEW_REQUIRED,
    "propose_hypotheses": EvidenceState.REVIEW_REQUIRED,
    "plan_experiments": EvidenceState.PLANNING,
    "execute": EvidenceState.PLANNING,
    "fable_reasoning": EvidenceState.PLANNING,
    "validate": EvidenceState.REVIEW_REQUIRED,
    "digest": EvidenceState.PLANNING,
    "draft_report": EvidenceState.REVIEW_REQUIRED,
    "ops_update": EvidenceState.REVIEW_REQUIRED,
}


def _stage_state(dry_run: bool, stage: str) -> str:
    return (_STAGE_DRY_RUN_STATE.get(stage, EvidenceState.REVIEW_REQUIRED) if dry_run
            else EvidenceState.BLOCKED).value


def _summarize_run_card(source_name: str, card: Any, dry_run: bool) -> Dict[str, Any]:
    """Run-card boundary: classify the card and admit its metrics only if evidence-ready.

    A dry run admits nothing. An evidence-ready card is downgraded to review_required, so
    no metric reaches the event log or any downstream stage from a planning-only run."""
    decision = classify_artifact(card)
    if dry_run and decision.evidence_ready:
        decision = EvidenceDecision(
            EvidenceState.REVIEW_REQUIRED, decision.reasons + ("dry_run_no_admission",)
        )
    run_id = _echoed_run_id(card)
    metrics = card.get("metrics") if isinstance(card, Mapping) else None
    return {"source": source_name, "run_id": run_id, **decision.to_dict(),
            "metrics": admit_metrics(decision, metrics)}


def _echoed_run_id(card: Any) -> Optional[str]:
    """The card's run id if it is a plain identifier, otherwise None (never echo free text)."""
    value = card.get("run_id") if isinstance(card, Mapping) else None
    return value if isinstance(value, str) and _RUN_ID_RE.fullmatch(value) else None


def _rejected_run_card(source_name: str, reason: str) -> Dict[str, Any]:
    decision = EvidenceDecision(EvidenceState.INVALID, (f"malformed_artifact:{reason}",))
    return {"source": source_name, "run_id": None, **decision.to_dict(), "metrics": None}


def _run_card_digest(run_cards_dir: Optional[Path]) -> Optional[str]:
    """Digest of each run-card file's relative path and bytes, or None without a card directory.

    Folded into the run id so that different card sets never share an output directory,
    event log, or ledger. Identical card sets still produce identical run ids."""
    if not run_cards_dir or not Path(run_cards_dir).exists():
        return None
    root = Path(run_cards_dir)
    entries = []
    for path in sorted(root.rglob("*.run.json")):
        try:
            content = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            content = "unreadable"
        entries.append([path.relative_to(root).as_posix(), content])
    return hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()


# ── Config / result types ─────────────────────────────────────────────────────

@dataclass
class OrchestratorConfig:
    dry_run: bool = True
    seed: int = 42
    run_cards_dir: Optional[Path] = None   # where to look for *.run.json
    out_base_dir: Optional[Path] = None    # defaults to outputs/orchestrator/
    ledger_path: Optional[Path] = None     # defaults to <run>/research_cycle.sqlite3


@dataclass
class ExperimentSpec:
    spec_id: str
    hypothesis: str
    mode: str
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OrchestratorResult:
    run_id: str
    out_dir: Path
    stages_completed: List[str]
    stages_failed: List[str]
    dry_run: bool
    artifacts: Dict[str, Path] = field(default_factory=dict)
    error: Optional[str] = None
    execution_state: str = "REVIEW_REQUIRED"
    scientific_evidence: bool = False
    ledger_path: Optional[Path] = None
    evidence_state: Optional[str] = None  # derived from dry_run when omitted
    # No independently approved scientific gate exists in this package, so these
    # are invariants rather than settings: construction rejects any other value.
    scientific_pass: bool = False
    formal_bayes_factor: None = None

    def __post_init__(self) -> None:
        if self.scientific_pass is not False:
            raise ValueError("scientific_pass must remain False: no independently approved scientific gate exists")
        if self.formal_bayes_factor is not None:
            raise ValueError("formal_bayes_factor must remain null in orchestrator results")
        if self.scientific_evidence is not False:
            raise ValueError("scientific_evidence must remain False for orchestrator results")
        if self.evidence_state is None:
            # Frozen dataclass: the derived value is set through object.__setattr__.
            object.__setattr__(self, "evidence_state", _run_evidence_state(self.dry_run, bool(self.stages_failed)).value)
        state = EvidenceState(self.evidence_state)
        allowed = DRY_RUN_STATES if self.dry_run else frozenset({EvidenceState.BLOCKED})
        if state not in allowed:
            raise ValueError(
                f"evidence_state {state.value!r} is not permitted for dry_run={self.dry_run}; "
                f"allowed: {sorted(s.value for s in allowed)}"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "out_dir": str(self.out_dir),
            "stages_completed": self.stages_completed,
            "stages_failed": self.stages_failed,
            "dry_run": self.dry_run,
            "artifacts": {k: str(v) for k, v in self.artifacts.items()},
            "error": self.error,
            "execution_state": self.execution_state,
            "evidence_state": self.evidence_state,
            "scientific_evidence": self.scientific_evidence,
            "scientific_pass": self.scientific_pass,
            "formal_bayes_factor": self.formal_bayes_factor,
            "ledger_path": str(self.ledger_path) if self.ledger_path else None,
        }


# ── Orchestrator ──────────────────────────────────────────────────────────────

class Orchestrator:
    def __init__(self, config: Optional[OrchestratorConfig] = None) -> None:
        self._cfg = config or OrchestratorConfig()

    def run_registered(self, request, registry, preflight_request, *, ledger_path: Path, now: str | None = None):
        """Execute an explicitly bound plan through canonical admission and runtime.

        Unlike the legacy template planning cycle, this entry point requires a
        complete caller-supplied plan and registered workload before execution.
        """
        from .registered_execution import execute_registered
        return execute_registered(request, registry, preflight_request, ledger_path, now=now)

    def run(
        self,
        dry_run: Optional[bool] = None,
        config: Optional[OrchestratorConfig] = None,
        _now: Optional[datetime] = None,
    ) -> OrchestratorResult:
        cfg = config or self._cfg
        if dry_run is not None:
            cfg = OrchestratorConfig(
                dry_run=dry_run,
                seed=cfg.seed,
                run_cards_dir=cfg.run_cards_dir,
                out_base_dir=cfg.out_base_dir,
                ledger_path=cfg.ledger_path,
            )

        now = _now or datetime.now(timezone.utc)
        run_id = self._make_run_id(cfg, now)

        from awareness_studio import config as app_config
        out_base = cfg.out_base_dir or (app_config.APP_ROOT / "outputs" / "orchestrator")
        out_dir = out_base / run_id
        out_dir.mkdir(parents=True, exist_ok=True)

        log = EventLog(out_dir)
        ledger_path = cfg.ledger_path or (out_dir / "research_cycle.sqlite3")
        ledger = ResearchCycleLedger(ledger_path)
        ledger_metadata = {"seed": cfg.seed, "dry_run": cfg.dry_run, "run_cards_dir": str(cfg.run_cards_dir) if cfg.run_cards_dir else None}
        ledger.create_cycle(run_id, metadata=ledger_metadata, producer="awareness_studio.orchestrator")
        self._seed_research_cycle(ledger, run_id, cfg, ledger_metadata)
        stages_completed: List[str] = []
        stages_failed: List[str] = []
        artifacts: Dict[str, Path] = {}
        context: Dict[str, Any] = {}

        stage_fns = {
            "ingest_inputs":      self._stage_ingest_inputs,
            "propose_hypotheses": self._stage_propose_hypotheses,
            "plan_experiments":   self._stage_plan_experiments,
            "execute":            self._stage_execute,
            "fable_reasoning":    self._stage_fable_reasoning,
            "validate":           self._stage_validate,
            "digest":             self._stage_digest,
            "draft_report":       self._stage_draft_report,
            "ops_update":         self._stage_ops_update,
        }

        for stage in PIPELINE_STAGES:
            fn = stage_fns[stage]
            t0 = time.monotonic()
            ledger.append_event(
                run_id,
                "orchestrator_stage",
                producer="awareness_studio.orchestrator",
                status="IN_PROGRESS",
                payload={"stage": stage, "dry_run": cfg.dry_run},
            )
            log.append(EventEnvelope.make(run_id, stage, "start", _now=now))
            try:
                result = fn(run_id, cfg, out_dir, context, _now=now)
                dur = (time.monotonic() - t0) * 1000
                result.setdefault("evidence_state", _stage_state(cfg.dry_run, stage))
                context[stage] = result
                artifacts.update(result.get("artifacts", {}))
                self._record_stage_result(ledger, run_id, stage, result, cfg, context)
                log.append(EventEnvelope.make(
                    run_id, stage, "ok",
                    payload={k: str(v) if isinstance(v, Path) else v
                             for k, v in result.items() if k != "artifacts"},
                    duration_ms=round(dur, 1),
                    _now=now,
                ))
                stages_completed.append(stage)
                ledger.append_event(
                    run_id,
                    "orchestrator_stage",
                    producer="awareness_studio.orchestrator",
                    status="COMPLETED",
                    payload={"stage": stage, "result": self._ledger_safe(result)},
                )
            except Exception as exc:
                dur = (time.monotonic() - t0) * 1000
                logger.exception("[orchestrator] stage %s failed", stage)
                log.append(EventEnvelope.make(
                    run_id, stage, "error",
                    error=str(exc),
                    duration_ms=round(dur, 1),
                    _now=now,
                ))
                stages_failed.append(stage)
                ledger.append_event(
                    run_id,
                    "orchestrator_stage",
                    producer="awareness_studio.orchestrator",
                    status="FAILED",
                    payload={"stage": stage, "reason": str(exc)},
                )
                break

        artifacts["events_jsonl"] = log.path
        artifacts["research_cycle_sqlite"] = ledger_path
        return OrchestratorResult(
            run_id=run_id,
            out_dir=out_dir,
            stages_completed=stages_completed,
            stages_failed=stages_failed,
            dry_run=cfg.dry_run,
            artifacts=artifacts,
            execution_state="REVIEW_REQUIRED" if cfg.dry_run else "NOT_IMPLEMENTED",
            scientific_evidence=False,
            ledger_path=ledger_path,
            evidence_state=_run_evidence_state(cfg.dry_run, bool(stages_failed)).value,
        )

    @staticmethod
    def _ledger_safe(value: Any) -> Any:
        """Project a stage result for the ledger. Metric values never enter the ledger here:
        promoting an evidence-ready metric into a claim-bearing record is a separate,
        reviewed step, so metrics are dropped at every depth."""
        if isinstance(value, Path):
            return value.as_posix()
        if isinstance(value, dict):
            return {
                str(key): Orchestrator._ledger_safe(item)
                for key, item in value.items()
                if key not in ("artifacts", "metrics")
            }
        if isinstance(value, list):
            return [Orchestrator._ledger_safe(item) for item in value]
        return value

    def _seed_research_cycle(self, ledger: ResearchCycleLedger, run_id: str, cfg: OrchestratorConfig, metadata: Dict[str, Any]) -> None:
        limitations = ("Planning/interface evidence only; no scientific execution or conclusion is established.",)
        snapshot_id = stable_id("snapshot", {"cycle_id": run_id, "metadata": metadata})
        source_hash = sha256_json({"cycle_id": run_id, "metadata": metadata})
        ledger.append_record(run_id, SourceSnapshot(snapshot_id, run_id, "awareness_studio://orchestrator-config", source_hash, "planning", EvidenceClass.ENGINEERING_FACT, "Orchestrator configuration and planning only.", limitations, metadata={"synthetic_demo": False, "network_access": False}), producer="awareness_studio.orchestrator")
        evidence_id = stable_id("evidence", {"cycle_id": run_id, "snapshot_id": snapshot_id})
        ledger.append_record(run_id, EvidenceRecord(evidence_id, run_id, (snapshot_id,), "A research cycle was configured for planning; no measurement was executed.", "planning", EvidenceClass.HYPOTHESIS, "Planning/interface behavior only.", limitations, {"scientific_evidence": False}, (snapshot_id,)), producer="awareness_studio.orchestrator")
        claim_id = stable_id("claim", {"cycle_id": run_id, "evidence_id": evidence_id})
        ledger.append_record(run_id, Claim(claim_id, run_id, "The configured pipeline can be represented as a reviewable plan.", (evidence_id,), EvidenceClass.HYPOTHESIS, "Software planning behavior only; not a claim about biology or experiment outcomes.", limitations, parent_ids=(evidence_id,)), producer="awareness_studio.orchestrator")

    def _record_stage_result(self, ledger: ResearchCycleLedger, run_id: str, stage: str, result: Dict[str, Any], cfg: OrchestratorConfig, context: Dict[str, Any]) -> None:
        """Project stage outputs into the canonical ledger without promoting them.

        Missing solver, run, artifact, and validation nodes are represented by
        explicit blocked/review events.  No placeholder checksum or fabricated
        RunRecord is created for work that did not execute.
        """
        producer = "awareness_studio.orchestrator"
        limitations = ("Planning/interface evidence only; no scientific execution or conclusion is established.",)
        records = ledger.records(run_id)
        record_by_type = {record.record_type: record for record in records}
        claim = record_by_type.get("claim")
        if stage == "propose_hypotheses" and claim is not None:
            for item in result.get("hypotheses", []):
                hypothesis_id = stable_id("hypothesis", {"cycle_id": run_id, "h_id": item.get("h_id"), "text": item.get("text")})
                ledger.append_record(run_id, LedgerHypothesis(hypothesis_id, run_id, str(item.get("text", "")), (claim.record_id,), claim_scope="Hypothesis proposal only; not an empirical result.", scientific_limitations=limitations, parent_ids=(claim.record_id,)), producer=producer)
        elif stage == "plan_experiments":
            hypotheses = {item.get("h_id"): item for item in context.get("propose_hypotheses", {}).get("hypotheses", [])}
            for item in result.get("experiment_specs", []):
                source_hypothesis = hypotheses.get(item.get("hypothesis"), {})
                hypothesis_id = stable_id("hypothesis", {"cycle_id": run_id, "h_id": item.get("hypothesis"), "text": source_hypothesis.get("text")})
                experiment_id = stable_id("experiment", {"cycle_id": run_id, "spec": item})
                ledger.append_record(run_id, LedgerExperimentSpec(experiment_id, run_id, (hypothesis_id,), str(item.get("mode", "undeclared")), item.get("params", {}), evidence_class=EvidenceClass.HYPOTHESIS, claim_scope="Experiment planning only; no execution result.", scientific_limitations=limitations, parent_ids=(hypothesis_id,)), producer=producer)
        elif stage == "execute":
            status = "BLOCKED" if cfg.dry_run else "NOT_IMPLEMENTED"
            # The BLOCKED ledger status for a dry run is pinned by an existing ledger
            # integration test; the evidence_state carried in the payload is planning.
            ledger.append_event(run_id, "execution_outcome", producer=producer, status=status, payload={"execution_state": "PLANNING_ONLY" if cfg.dry_run else "NOT_IMPLEMENTED", "evidence_state": (EvidenceState.PLANNING if cfg.dry_run else EvidenceState.BLOCKED).value, "scientific_evidence": False, "results": self._ledger_safe(result.get("results", [])), "reason": "No solver was invoked; no RunRecordV1 was fabricated."})
        elif stage == "digest":
            paths = {key: str(value) for key, value in result.get("artifacts", {}).items()}
            ledger.append_event(run_id, "planning_artifact", producer=producer, status="REVIEW_REQUIRED", payload={"planning_only": True, "evidence_state": EvidenceState.PLANNING.value if cfg.dry_run else EvidenceState.BLOCKED.value, "scientific_evidence": False, "artifact_paths": paths, "reason": "These are interface/report artifacts, not scientific measurements."})
            ledger.append_event(run_id, "evidence_graph_update", producer=producer, status="REVIEW_REQUIRED", payload={"planning_only": True, "evidence_state": EvidenceState.PLANNING.value if cfg.dry_run else EvidenceState.BLOCKED.value, "scientific_evidence": False, "reason": "Graph contains proposed hypotheses only."})
        elif stage == "validate":
            ledger.append_event(run_id, "validation_outcome", producer=producer, status="REVIEW_REQUIRED" if cfg.dry_run else "NOT_IMPLEMENTED", payload={"validation_status": "REVIEW_REQUIRED" if cfg.dry_run else "NOT_IMPLEMENTED", "evidence_state": EvidenceState.REVIEW_REQUIRED.value if cfg.dry_run else EvidenceState.BLOCKED.value, "scientific_evidence": False, "checks": self._ledger_safe(result.get("checks", [])), "reason": "Planning output cannot validate scientific execution."})
        elif stage == "ops_update":
            ledger.append_event(run_id, "release_review", producer=producer, status="REVIEW_REQUIRED", payload={"release_state": "REVIEW_REQUIRED", "evidence_state": EvidenceState.REVIEW_REQUIRED.value if cfg.dry_run else EvidenceState.BLOCKED.value, "execution_allowed": False, "scientific_evidence": False, "reason": "No autonomous release or claim promotion is permitted."})

    # ── Stage implementations ─────────────────────────────────────────────────

    def _stage_ingest_inputs(
        self, run_id: str, cfg: OrchestratorConfig, out_dir: Path,
        ctx: Dict[str, Any], *, _now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        # Run cards are untrusted inputs. They are classified here, and only the
        # classification plus evidence-ready metrics leaves this stage. The raw
        # card (and any unadmitted metric value) is never forwarded downstream.
        summaries: List[Dict[str, Any]] = []
        loaded = 0
        if cfg.run_cards_dir and Path(cfg.run_cards_dir).exists():
            for p in sorted(Path(cfg.run_cards_dir).rglob("*.run.json")):
                try:
                    text = p.read_text(encoding="utf-8")
                except OSError:
                    summaries.append(_rejected_run_card(p.name, "unreadable_file"))
                    continue
                try:
                    card = json.loads(text)
                except (ValueError, RecursionError):
                    # ValueError covers invalid JSON; RecursionError covers absurd nesting.
                    summaries.append(_rejected_run_card(p.name, "malformed_json"))
                    continue
                loaded += 1
                summaries.append(_summarize_run_card(p.name, card, cfg.dry_run))
        return {
            "run_cards_loaded": loaded,
            "run_cards": summaries,
            "run_cards_evidence_ready": sum(1 for item in summaries if item["evidence_ready"]),
            "dry_run": cfg.dry_run,
        }

    def _stage_propose_hypotheses(
        self, run_id: str, cfg: OrchestratorConfig, out_dir: Path,
        ctx: Dict[str, Any], *, _now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        hypotheses = [
            {
                "h_id": "h001",
                "text": "Vedana (sensation tone) modulates tanha (craving) via gain-control dynamics.",
                "confidence": "medium",
                "source": "template",
                "proposal_only": True,
                "mutates_claims": False,
            },
            {
                "h_id": "h002",
                "text": "Upadana (clinging) functions as a latching mechanism stabilized by samsaric loops.",
                "confidence": "low",
                "source": "template",
                "proposal_only": True,
                "mutates_claims": False,
            },
        ]
        return {"hypotheses": hypotheses, "count": len(hypotheses)}

    def _stage_plan_experiments(
        self, run_id: str, cfg: OrchestratorConfig, out_dir: Path,
        ctx: Dict[str, Any], *, _now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        specs = [
            ExperimentSpec(
                spec_id=f"exp_{run_id[:8]}_001",
                hypothesis="h001",
                mode="psi",
                params={"N": 64, "n_steps": 50, "seed": cfg.seed},
            ),
            ExperimentSpec(
                spec_id=f"exp_{run_id[:8]}_002",
                hypothesis="h002",
                mode="meditation",
                params={"n_epochs": 30, "seed": cfg.seed},
            ),
        ]
        return {
            "experiment_specs": [
                {"spec_id": s.spec_id, "hypothesis": s.hypothesis,
                 "mode": s.mode, "params": s.params, "planning_only": True,
                 "mutates_claims": False}
                for s in specs
            ],
            "count": len(specs),
        }

    def _stage_execute(
        self, run_id: str, cfg: OrchestratorConfig, out_dir: Path,
        ctx: Dict[str, Any], *, _now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        specs = ctx.get("plan_experiments", {}).get("experiment_specs", [])
        results = []
        for spec in specs:
            if cfg.dry_run:
                results.append({
                    "spec_id": spec["spec_id"],
                    "mode": spec["mode"],
                    "status": "PLANNING_ONLY",
                    "planning_only": True,
                    "scientific_evidence": False,
                    "reason": "Dry-run plans the execution interface and invokes no solver.",
                })
            else:
                results.append({
                    "spec_id": spec["spec_id"],
                    "mode": spec["mode"],
                    "status": "NOT_IMPLEMENTED",
                    "scientific_evidence": False,
                    "reason": "Live solver execution is not implemented by Awareness Studio.",
                })
        for item in results:
            item["evidence_state"] = _stage_state(cfg.dry_run, "execute")
        return {"results": [self._admit_result(item, cfg.dry_run) for item in results], "dry_run": cfg.dry_run}

    @staticmethod
    def _admit_result(result: Dict[str, Any], dry_run: bool) -> Dict[str, Any]:
        """Metric admission chokepoint. A dry run admits no metric: values become null and the
        state stays planning. A live result keeps its metrics only when an evidence-ready
        decision covers them, and its state comes from the classification."""
        if "metrics" not in result:
            return result
        if dry_run:
            return {**result, "metrics": None, "evidence_state": _stage_state(True, "execute")}
        decision = classify_artifact({"run_id": result.get("spec_id"), **result})
        return {**result, "metrics": admit_metrics(decision, result["metrics"]),
                "evidence_state": decision.state.value}

    def _stage_fable_reasoning(
        self, run_id: str, cfg: OrchestratorConfig, out_dir: Path,
        ctx: Dict[str, Any], *, _now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Fable 5-powered metric interpretation over the execute stage's results.

        `llm_reasoning.fable_interpreter.FableInterpreter` makes a real
        Anthropic API call, which would violate this orchestrator's
        dry_run=True contract ("No network or LLM calls required"). Mirrors
        `_stage_execute`'s dry_run/live split: a deterministic stub in
        dry_run (what every current caller/test exercises), "not_implemented"
        live (wiring the real call is a separate feature decision).
        """
        results = ctx.get("execute", {}).get("results", [])
        interpretations = []
        for r in results:
            if cfg.dry_run:
                interpretations.append({
                    "spec_id": r.get("spec_id"),
                    "status": "PLANNING_ONLY",
                    "scientific_evidence": False,
                    "reason": "No LLM call made; planning output is not evidence.",
                })
            else:
                interpretations.append({
                    "spec_id": r.get("spec_id"),
                    "status": "NOT_IMPLEMENTED",
                    "scientific_evidence": False,
                })
        return {"interpretations": interpretations, "dry_run": cfg.dry_run}

    def _stage_validate(
        self, run_id: str, cfg: OrchestratorConfig, out_dir: Path,
        ctx: Dict[str, Any], *, _now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        results = ctx.get("execute", {}).get("results", [])
        checks: List[Dict] = []
        for r in results:
            passed = False
            checks.append({
                "spec_id": r.get("spec_id"),
                "passed": passed,
                "status": "REVIEW_REQUIRED" if cfg.dry_run else "NOT_IMPLEMENTED",
                "scientific_evidence": False,
                "note": "planning/interface evidence only" if cfg.dry_run else "solver execution not implemented",
            })
        all_passed = all(c["passed"] for c in checks)
        # A non-passing planning check is an explicit review state, not a stage
        # exception.  This keeps the pipeline auditable without manufacturing a
        # scientific failure or success.
        return {"checks": checks, "all_passed": all_passed}

    def _stage_digest(
        self, run_id: str, cfg: OrchestratorConfig, out_dir: Path,
        ctx: Dict[str, Any], *, _now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        hypotheses = ctx.get("propose_hypotheses", {}).get("hypotheses", [])
        results = ctx.get("execute", {}).get("results", [])

        # Write EvidenceLogDraft.md
        evidence_path = out_dir / "EvidenceLogDraft.md"
        lines = [
            f"# Evidence Log Draft — run {run_id}",
            "",
            f"**Generated:** {(_now or datetime.now(timezone.utc)).isoformat()}  ",
            f"**Dry run:** {cfg.dry_run}",
            "**Scientific pass:** `false`; **formal Bayes factor:** `null`",
            "",
            "## Hypotheses",
            "",
        ]
        for h in hypotheses:
            lines += [
                f"### {h['h_id']}: {h['text']}",
                f"- Confidence: {h['confidence']}",
                f"- Source: {h['source']}",
                "",
            ]
        lines += ["## Experiment Results", ""]
        for r in results:
            lines += [
                f"### {r.get('spec_id', '?')}",
                f"- Mode: {r.get('mode')}",
                f"- Status: {r.get('status')}",
                f"- Evidence state: {r.get('evidence_state')}",
            ]
            if "metrics" in r:
                lines.append(f"- Metrics: {_format_metrics(r['metrics'])}")
            lines.append("")
        evidence_path.write_text("\n".join(lines), encoding="utf-8")

        # Write GraphUpdate.json
        graph_path = out_dir / "GraphUpdate.json"
        graph = {
            "run_id": run_id,
            "nodes": [{"id": h["h_id"], "label": h["text"], "type": "hypothesis"}
                      for h in hypotheses],
            "edges": [],
            "updated_at": (_now or datetime.now(timezone.utc)).isoformat(),
        }
        graph_path.write_text(json.dumps(graph, indent=2), encoding="utf-8")

        return {
            "artifacts": {
                "EvidenceLogDraft.md": evidence_path,
                "GraphUpdate.json": graph_path,
            }
        }

    def _stage_draft_report(
        self, run_id: str, cfg: OrchestratorConfig, out_dir: Path,
        ctx: Dict[str, Any], *, _now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        hypotheses = ctx.get("propose_hypotheses", {}).get("hypotheses", [])
        results = ctx.get("execute", {}).get("results", [])
        checks = ctx.get("validate", {}).get("checks", [])
        n_pass = sum(1 for c in checks if c["passed"])

        report_path = out_dir / "Report.md"
        lines = [
            f"# Orchestrator Report — {run_id}",
            "",
            f"**Date:** {(_now or datetime.now(timezone.utc)).isoformat()}  ",
            f"**Mode:** {'dry-run' if cfg.dry_run else 'live'}  ",
            f"**Evidence state:** {(EvidenceState.PLANNING if cfg.dry_run else EvidenceState.BLOCKED).value}  ",
            "**Scientific pass:** `false`; **formal Bayes factor:** `null`  ",
            f"**Stages:** {len(PIPELINE_STAGES)} planned; execution state is review-only  ",
            f"**Validation:** {n_pass}/{len(checks)} checks passed; planning output is not scientific evidence",
            "",
            "## Summary",
            "",
            f"This orchestrator run processed {len(hypotheses)} hypotheses across "
            f"{len(results)} experiment specs.",
            "",
            "## Hypotheses Evaluated",
            "",
        ]
        for h in hypotheses:
            lines.append(f"- **{h['h_id']}** ({h['confidence']}): {h['text']}")
        lines += [
            "",
            "## Validation Status",
            "",
        ]
        for c in checks:
            mark = "REVIEW_REQUIRED" if not c["passed"] else "COMPLETED"
            lines.append(f"- [{mark}] {c['spec_id']} — {c['note']}")
        lines += [
            "",
            "## Artifacts",
            "",
            f"All outputs in: `outputs/orchestrator/{run_id}/`",
            "",
            "| File | Description |",
            "|------|-------------|",
            "| events.jsonl | Append-only event log |",
            "| EvidenceLogDraft.md | Draft evidence card entries |",
            "| GraphUpdate.json | Knowledge graph delta |",
            "| Report.md | This report |",
            "| OpsQueueItem.json | Ops sync payload |",
        ]
        report_path.write_text("\n".join(lines), encoding="utf-8")

        return {"artifacts": {"Report.md": report_path}}

    def _stage_ops_update(
        self, run_id: str, cfg: OrchestratorConfig, out_dir: Path,
        ctx: Dict[str, Any], *, _now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        ops_path = out_dir / "OpsQueueItem.json"
        item = {
            "run_id": run_id,
            "task": f"Review orchestrator output for run {run_id[:8]}",
            "priority": "normal",
            "status": "pending",
            "dry_run": cfg.dry_run,
            "evidence_state": _stage_state(cfg.dry_run, "ops_update"),
            "scientific_pass": False,
            "formal_bayes_factor": None,
            "links": {
                "report": str(out_dir / "Report.md"),
                "evidence": str(out_dir / "EvidenceLogDraft.md"),
            },
            "created_at": (_now or datetime.now(timezone.utc)).isoformat(),
            "airtable_payload": {
                "table": "Work Queue",
                "action": "planning_only" if cfg.dry_run else "not_implemented",
                "fields": {
                    "task": f"Orchestrator run {run_id[:8]}",
                    "priority": "normal",
                    "status": "pending",
                    "links": str(out_dir),
                },
            },
        }
        ops_path.write_text(json.dumps(item, indent=2), encoding="utf-8")
        return {"artifacts": {"OpsQueueItem.json": ops_path}}

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _make_run_id(cfg: OrchestratorConfig, now: datetime) -> str:
        d: dict = {"seed": cfg.seed, "dry_run": cfg.dry_run}
        if not cfg.dry_run:
            d["ts"] = now.isoformat()
        cards_digest = _run_card_digest(cfg.run_cards_dir)
        if cards_digest is not None:
            d["run_cards_sha256"] = cards_digest
        blob = json.dumps(d, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]
