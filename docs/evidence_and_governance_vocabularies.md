# Evidence and Governance Vocabularies — Architecture Landscape

**Purpose:** Document why NeuroTopology-Sim has four independent evidence/state classification vocabularies, why their separation is intentional, and how they coordinate.

**Status:** This document describes systems as they exist 2026-09-14. It is not a design proposal but an audit of actual code behavior.

---

## Overview

The repository contains four independent evidence/governance classification systems:

1. **Transition Artifacts** (transitions/, phase_space/) — computational transitions and derived coordinates
2. **Research Claim Promotion** (sciencer_d/btc_icft/ontology/) — DS005620 M/T/C/Q/O research claim gates
3. **Literature Source Classification** (tools/literature_senses/) — literature metadata and evidence tiers
4. **PR/CI State** (tools/integration_reconciliation/) — pull request and CI check classification

Each system:
- Serves a distinct domain (artifact governance, research claim gates, literature metadata, PR mergeability)
- Uses its own vocabulary by design, not by accident
- Does NOT translate to other systems' vocabularies
- Has no known maintenance burden from coexistence

---

## System 1: Transition Artifacts (transitions/, phase_space/)

**Purpose:** Govern computational artifacts (TransitionRecordV1, PhaseSpaceCoordinateV1) produced by exporters, and track claim ceilings through the artifact pipeline.

**Vocabularies:**

### claim_scope (TransitionRecordV1.claim_scope)
```python
# transitions/governance.py
ALLOWED_CLAIM_SCOPES = frozenset({
    "computational_artifact",      # test infrastructure, experiment harness
    "exploratory_metric",          # post-hoc metric discovery on a dataset
    "dataset_specific",            # effect found on one specific dataset
    "cross_subject_dataset_specific",  # effect replicated across subjects in one dataset
})

BLOCKED_CLAIM_SCOPES = frozenset({
    "clinical", "diagnostic", "treatment", "consciousness_biomarker",
    "mechanistic_causal", "spiritual_attainment", "enlightenment_detection",
    "jhana_detection", "cessation_detection",
})
```

### evidence_level (TransitionRecordV1.evidence_level)
```python
# transitions/governance.py
ALLOWED_EVIDENCE_LEVELS = frozenset({
    "L0_computational_artifact",    # synthetic benchmark, CI test
    "L1_synthetic_validation",      # algorithm validation on synthetic data
    "L2_single_subject_real_signal",  # real signal, one subject, offline
    "L3_dataset_specific_effect",   # real effect on one dataset
    "L4_cross_subject_dataset_specific",  # real effect across subjects
})
```

**Why separate from other systems:**
- These govern *computational artifacts*, not research claims or literature metadata
- The hierarchy (L0→L4) reflects confidence in an artifact's realism, not a claim's evidence strength
- Used by exporters, transition stores, and phase-space coordinate builders — pure artifact governance

**Links to other systems:**
- Phase-space coordinates read TransitionRecordV1.claim_scope/evidence_level as inputs
- Ontology evaluation *could* consume these but currently doesn't (evidence bundles decouple them)

---

## System 2: Research Claim Promotion (sciencer_d/btc_icft/ontology/)

**Purpose:** Gate which research claim types are permissible given available artifacts, controls, and datasets. Enforces empirical, mechanistic, and theoretical claim guardrails.

**Vocabularies:**

### ClaimScope (ontology/schema.py)
```python
class ClaimScope:
    ENGINEERING_RUNTIME = "engineering_runtime"        # tool/test passes, no claims
    MARKER_ASSOCIATION = "marker_association"          # M-layer: signal markers
    TOPOLOGY_RESIDUAL = "topology_residual"            # T-layer: topological residual
    MECHANISM_CANDIDATE = "mechanism_candidate"        # C-layer: substrate mechanism candidate
    THEORY_CONSISTENCY = "theory_consistency"          # Q-layer: theory-consistency check
    ONTOLOGY_CANDIDATE = "ontology_candidate"          # O-layer: ontology hypothesis
    BLOCKED_OVERREACH = "blocked_overreach"            # claim scope too high for evidence
    REJECTED = "rejected"                              # claim permanently ineligible
```

### PromotionState (ontology/schema.py)
```python
class PromotionState:
    DRAFT = "draft"
    ENGINEERING_VALIDATED = "engineering_validated"
    EMPIRICAL_CANDIDATE = "empirical_candidate"
    EMPIRICAL_SUPPORTED_LIMITED = "empirical_supported_limited"
    MECHANISM_CANDIDATE = "mechanism_candidate"
    THEORY_CONSISTENCY_ONLY = "theory_consistency_only"
    ONTOLOGY_QUARANTINED = "ontology_quarantined"
    BLOCKED_PENDING_REAL_EXECUTION = "blocked_pending_real_execution"
    BLOCKED_PENDING_CONTROLS = "blocked_pending_controls"
    BLOCKED_PENDING_REVIEW = "blocked_pending_review"
    BLOCKED_OVERREACH = "blocked_overreach"
    REJECTED = "rejected"
```

### OntologyLayer (ontology/schema.py)
```python
class OntologyLayer:
    D_PHENOMENOLOGY = "D_PHENOMENOLOGY"
    M_MARKER = "M_MARKER"
    T_TOPOLOGY = "T_TOPOLOGY"
    C_SUBSTRATE = "C_SUBSTRATE"
    Q_THEORY = "Q_THEORY"
    O_ONTOLOGY_CANDIDATE = "O_ONTOLOGY_CANDIDATE"
    OMEGA_GOVERNANCE = "OMEGA_GOVERNANCE"
```

**Why separate from other systems:**
- These are *research-specific* claim gates, not artifact governance (transitions) or literature metadata
- Defined by `determine_promotion_state()` logic based on **runtime mode, available artifacts, controls, datasets, and human review**
- The M/T/C/Q/O layers encode the specific scientific hierarchy this repository enforces
- No translation needed: a research artifact is evaluated directly using ontology.promotion logic

**Links to other systems:**
- Reads run_mode (synthetic vs. real), available_artifacts (files written), available_controls (nulls/ablations/leakage report)
- Outputs claim_scope and promotion_state for the OntologyResult
- Does NOT consume literature_senses tiers or transitions claim_scope directly

---

## System 3: Literature Source Classification (tools/literature_senses/)

**Purpose:** Classify literature sources by evidence tier for retrieval-augmented generation (RAG) and literature-to-research-construct mapping.

**Vocabularies:**

### evidence_tier (schema.py:BaseRecord)
```python
@dataclass
class BaseRecord:
    evidence_tier: str = "T0_speculative_conceptual"  # TN tier system
    # Additional metadata:
    evidence_state: str = "metadata_only"
    relevance_score: float = 0.0
    novelty_score: float = 0.0
    method_quality_score: float = 0.0
    falsifier_value: float = 0.0
    integration_value: float = 0.0
    safety_value: float = 0.0
```

**Why separate from other systems:**
- Classifies *literature sources*, not research artifacts or computational artifacts
- TN tier system reflects publication/database confidence levels, not experimental claims
- Used by RAG retrieval and literature-bridge mappings to filter/weight sources
- Independent from research claim promotion (literature can be speculative; research claims must be gated)

**Links to other systems:**
- Literature sources are *inputs* to research hypotheses, not research claims themselves
- Mapped into research_cycle ledgers via tools/literature_bridge
- Do NOT gate research claim scope/promotion directly

---

## System 4: PR/CI State Classification (tools/integration_reconciliation/)

**Purpose:** Classify pull request and CI check state to determine merge readiness and identify infrastructure vs. code problems.

**Vocabularies:**

### checks_status (ci_interpretation.py)
```python
CLASSIFICATIONS = frozenset({
    "passing",                    # CI check passed
    "failing",                    # CI check failed (code problem)
    "pending",                    # CI check not yet completed
    "not_run",                    # CI check was never executed
    "infrastructure_blocked",     # CI job blocked by infrastructure (disk, runner, network)
    "billing_blocked",            # CI job blocked by billing/payment issue
    "unknown",                    # Could not classify this check
})
```

### mergeability (models.py)
```python
CurrentStatus.mergeability: str  # "mergeable" | "conflicting" | "unknown"
```

### lifecycle_state (models.py)
```python
CurrentStatus.lifecycle_state: str  # "draft" | "open" | "closed" | "merged" | None
```

### STAGES (models.py)
```python
STAGES = (
    "reported",         # PR exists in work orders
    "branch_present",   # Git branch exists locally
    "pr_present",       # PR exists on GitHub
    "checks_passing",   # CI checks passing
    "mergeable",        # Git merge is possible (no conflicts)
    "merged",           # PR is merged into target branch
)
```

**Why separate from other systems:**
- Classifies *PR/CI infrastructure state*, not research evidence or artifact governance
- Distinguishes real code failures from infrastructure problems (disk space, runner health, billing)
- Used for PR reconciliation and merge readiness assessment
- No overlap with research, artifact, or literature vocabularies

**Links to other systems:**
- Used by Awareness Studio's orchestration layer to track research execution PRs
- Does NOT influence research claim promotion decisions
- CI failures can block a PR, but don't directly gate claim scope

---

## Coordination: How Systems Work Together

```
Literature Source (literature_senses)
    ├─ evidence_tier, evidence_state
    └─ Retrieved for RAG context

        ↓ (mapped via literature_bridge)

Research Hypothesis + Experimental Plan
    ├─ Transition Artifacts (transitions/)
    │   ├─ claim_scope: computational_artifact → dataset_specific → cross_subject_dataset_specific
    │   ├─ evidence_level: L0 → L4
    │   └─ Exported for reproducibility
    │
    └─ GitHub PR (integration_reconciliation/)
        ├─ lifecycle_state: draft → open → merged
        ├─ checks_status: pending → passing/failing
        └─ mergeability: mergeable/conflicting
        
        ↓ (when merged)

Research Claim Promotion (ontology/)
    ├─ Input: run_mode (synthetic/real), available_artifacts, controls
    ├─ determine_promotion_state() → PromotionState
    ├─ determine_max_claim_scope() → ClaimScope (M/T/C/Q/O)
    └─ OntologyResult with gates enforced

        ↓ (output)

Governed Evidence Bundle
    └─ Records: artifacts used, registry decisions, transition IDs,
       claim ceiling, promotion state — reproducible manifest
```

**Key principle:** Each system operates in its own domain and is queried independently. There is no translation layer because systems don't need to speak each other's vocabulary.

---

## Why Separation Is Intentional, Not Duplication

From transitions/governance.py (lines 1-16):

> "The repository already has a claim/promotion taxonomy for the DS005620 M/T/C/Q/O ontology track... but its eight values encode a different, narrower promotion ladder for that specific label-contract track and do not cover this package's transition-artifact scopes... Rather than force-fit an unrelated vocabulary, this module defines its own — deliberately small and explicit."

**This design decision reflects:**
1. **Different domains require different semantics** — artifact confidence (L0→L4) ≠ research claim scope (ENGINEERING_RUNTIME → ONTOLOGY_CANDIDATE)
2. **Separation prevents cross-domain corruption** — a synthetic benchmark (L0_computational_artifact) can never accidentally be promoted to a research claim
3. **Each system can evolve independently** — future evidence levels, claim scopes, or CI states don't require renegotiating shared vocabulary

**No maintenance burden:** No code translates between these vocabularies, and none needs to. Systems either use one vocabulary or the other, never both for the same decision.

---

## Potential Future Work

If future work introduces **actual overlap** (two systems needing to describe the same concept), this document should be updated to:
1. Document the overlap and why unification is justified
2. Define a mapping layer or shared enum (if needed)
3. Explain the tradeoffs (shared vocabulary → easier reasoning; separate → independent evolution)

**Current state:** No such overlap has emerged. Systems remain independent.

---

## References

- `transitions/governance.py` — design rationale for separate transition vocabularies
- `sciencer_d/btc_icft/ontology/schema.py` — claim scope and promotion state definitions
- `tools/literature_senses/schema.py` — literature evidence tier definition
- `tools/integration_reconciliation/ci_interpretation.py` — CI check classification
- `docs/governed_evidence_bundles.md` — evidence bundle coordination
