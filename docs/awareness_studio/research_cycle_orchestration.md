# Awareness Studio Research-Cycle Orchestration — Contract

Owner: `tools/awareness_studio_research_loop/**`, `scripts/run_awareness_research_cycle.py`, `tests/awareness_studio_research_loop/**`.

## What this orchestrator does

A deterministic tool that reads local JSON/YAML evidence documents already
produced by other systems and compiles them into one cycle-state
assessment per hypothesis, one artifact ledger, and one paper-ready
Markdown draft — without ever discovering or executing arbitrary code,
without ever letting an unsupported claim present itself as a scientific
conclusion, and **without ever certifying scientific truth itself**. It
proposes and organizes research direction; a human decides what to
believe.

## Ownership boundaries

- The literature registry (`tools/awareness_studio_research/**`) is owned
  by Claude A. Not modified, not imported. Consumed only through the
  `literature_evidence` JSON contract below, shaped to match that
  package's own record types (`LiteratureSource`, `ExtractedClaim`,
  `HypothesisLink`, `ExperimentLink`, `EvidenceUpdate`) so a real export
  from that system can be pointed at directly.
- The hypothesis registry is owned by Antigravity C. Not modified, not
  imported. Consumed only through the `hypothesis_registry` JSON contract.
- `tools/research_cycle/**`, `tools/research_record/**`,
  `tools/release_manifest/**`, scientific solvers, the Bayesian
  falsification implementation, topology algorithms, and dashboard routes
  are not modified, imported, or depended on.
- `obsidian/15_DS005620_Post_Execution_Controls/Execution_Artifact_Audit.md`
  and `outputs/command_center/mock_payloads/guardrails_status.json` are
  explicitly preserved — outside this package's owned paths, never
  touched.

## Non-goals

- No network access, no `git`/`gh` invocations, no solver imports, no
  automatic directory scanning, and — critically for this orchestrator —
  **no execution of anything it reads**. It parses data formats
  (JSON/YAML/CSV) only; nothing in the pipeline ever calls `exec`,
  `eval`, `subprocess`, or imports a module named by input data.
- No heavy scientific solvers. Nothing here imports `mne`, `scipy`,
  `torch`, `ripser`, `gudhi`, `boto3`, `botocore`, or `sklearn` — verified
  by a static AST import scan and an isolated subprocess run of the CLI
  (`tests/awareness_studio_research_loop/test_no_heavy_imports.py`).

## Pipeline stages (requirement 1)

```
literature evidence → claim graph → hypothesis selection
  → experiment-plan validation → simulation/analysis execution
  → null/surrogate validation → evidence update → theory revision
  → paper/report draft
```

Each stage corresponds to one or more input sections and one link in the
per-hypothesis cycle-state ladder (`state_machine.py`):

| Stage | Input section(s) | Ladder rung |
|---|---|---|
| Literature evidence | `literature_evidence` (sources, claims) | `LITERATURE_READY` |
| Claim graph | `literature_evidence` (hypothesis_links, experiment_links) | merged into each hypothesis's `claim_ids` |
| Hypothesis selection | `hypothesis_registry` | `HYPOTHESIS_READY` |
| Experiment-plan validation | `experiment_plans` | `EXPERIMENT_READY` |
| Simulation/analysis execution | `execution_results` | `EXECUTION_PENDING` → `EXECUTED` |
| Null/surrogate validation | `null_surrogate_results` | `VALIDATION_PENDING` → `INCONCLUSIVE` or continue |
| Evidence update | `literature_evidence` (evidence_updates) | `EVIDENCE_UPDATE_READY` |
| Theory revision | `theory_state` | `THEORY_REVISION_REQUIRED` (if triggered) |
| Paper/report draft | `reviewer_decisions` gate, then the draft itself | `HUMAN_REVIEW_REQUIRED` or `PAPER_DRAFT_READY` |

## Input manifest

A manifest file (JSON or YAML) maps input-contract names to file paths
(relative paths resolve against the manifest's own directory). Every key
is optional; an absent, malformed, or non-finite-containing file produces
`"available": false` rather than aborting the whole compile.

```json
{
  "literature_evidence": "evidence/literature_evidence.json",
  "hypothesis_registry": "evidence/hypothesis_registry.json",
  "experiment_plans": "evidence/experiment_plans.json",
  "execution_results": "evidence/execution_results.json",
  "null_surrogate_results": "evidence/null_surrogate_results.json",
  "validation_reports": "evidence/validation_reports.json",
  "reviewer_decisions": "evidence/reviewer_decisions.json",
  "theory_state": "evidence/theory_state.json",
  "cycle_config": "evidence/cycle_config.json"
}
```

### Input contract shapes

**`literature_evidence`** (flat object, JSON/YAML only — no natural single
row-list) — `{"sources": [...], "claims": [...], "hypothesis_links": [...], "experiment_links": [...], "evidence_updates": [...]}`:

- `sources[]`: `{source_id, title, doi, source_checksum, evidence_tier, verification_status, status, limitations}`. `evidence_tier` ∈ `{T1_verified_primary, T2_verified_secondary, T3_unverified_claimed, T4_disputed}`; `verification_status` ∈ `{verified, unverified, disputed}` — the exact vocabulary `tools/awareness_studio_research/models.py` uses.
- `claims[]`: `{claim_id, source_id, claim_text, claim_class, claim_status, linked_hypothesis}`. `claim_status` ∈ `{empirical, theoretical, proxy, speculative, unsupported}` — this **is** the claim's evidence class; nothing here reclassifies it.
- `hypothesis_links[]` / `experiment_links[]`: `{hypothesis_id | experiment_ref, claim_ids: [...], relationship}` — the claim graph. A hypothesis's effective `claim_ids` is the union of its own registry field and every `hypothesis_links` entry naming it.
- `evidence_updates[]`: `{update_id, entity_type, entity_id, update_type, reason}`. `update_type` ∈ `{created, downgraded, superseded, disputed, amended}`. An `entity_type="hypothesis"` update is what advances a hypothesis past `EVIDENCE_UPDATE_READY`.

**`hypothesis_registry`** — `{"hypotheses": [{hypothesis_id, statement, claim_ids, null_prediction, falsification_criterion}]}`. **Gate: every hypothesis must have a non-empty `null_prediction`.**

**`experiment_plans`** — `{"plans": [{experiment_id, hypothesis_id, falsification_criterion, metrics: [{name, unit, feature_family}], dataset_id, dataset_checksum, held_out_split_locked, is_predictive, preregistered, synthetic}]}`. **Gates: every experiment must have a `falsification_criterion`; every metric must declare `unit` and `feature_family`; every `is_predictive` plan must have `held_out_split_locked: true`.**

**`execution_results`** — `{"executions": [{experiment_id, status, data_mode, input_checksums, output_checksums, software_commit, runtime_seconds, dependency_state, metric_values: [{name, value, unit}]}]}`. `status` ∈ `{completed, failed, running, not_started}`; `data_mode` ∈ `{synthetic, proxy, empirical, unknown}`. **Gate: every `data_mode=empirical` execution must have a dataset checksum (on its plan) and non-empty `output_checksums`.**

**`null_surrogate_results`** — `{"null_tests": [{experiment_id, method, verdict, statistic, notes}]}`. `verdict` ∈ `{PASS, FAIL, INCONCLUSIVE, TIMEOUT}` — `TIMEOUT` is a distinct outcome from all three others and never counted as a scientific result.

**`validation_reports`** — `{"reports": [{report_id, experiment_id, claim_status, data_mode, verdict, source}]}` — a generic reference to external validation (e.g. another compiler's output), read only as data. **Gate: a report must never claim `data_mode=empirical` for an experiment whose own execution is `data_mode=synthetic`** (a synthetic result remains synthetic).

**`reviewer_decisions`** — `{"decisions": [{subject_type, subject_id, decision, reviewer, notes}]}`. `subject_type` ∈ `{claim, hypothesis, experiment, paper_claim}`; `decision` ∈ `{approved, rejected, pending, not_required}`. No hypothesis reaches `PAPER_DRAFT_READY` without an `approved` (or `not_required`) decision recorded for it — an absent decision is treated as `pending`, never as implicit approval.

**`theory_state`** (flat) — `{theory_id, version, statements: [...], contradictory_evidence_ids: [...], alternative_explanations: [...]}`. **Gate: every `contradictory_evidence_ids` entry must still resolve to a known claim** — a theory update may never silently drop the evidence that contradicts it.

**`cycle_config`** (flat, optional) — `{research_question, repo}`.

## Cycle states (requirement 3)

Computed once per hypothesis by `state_machine.compute_cycle_state`, never
stored or trusted from an input — an upstream system cannot simply assert
`PAPER_DRAFT_READY`:

`LITERATURE_READY`, `HYPOTHESIS_READY`, `EXPERIMENT_READY`,
`EXECUTION_PENDING`, `EXECUTED`, `VALIDATION_PENDING`,
`EVIDENCE_UPDATE_READY`, `THEORY_REVISION_REQUIRED`, `PAPER_DRAFT_READY`,
`BLOCKED_BY_PROVENANCE`, `BLOCKED_BY_DATA`, `BLOCKED_BY_DEPENDENCY`,
`HUMAN_REVIEW_REQUIRED`, `INCONCLUSIVE`.

The waterfall (see `state_machine.py` for the exact, commented logic)
checks blocking conditions first (provenance → dependency → data), then
climbs the ladder above one rung at a time, stopping at the first
unsatisfied gate. A hypothesis with **no** linked literature claims at all
returns `HUMAN_REVIEW_REQUIRED` rather than vacuously passing the
provenance gate — a hypothesis with zero grounding needs a human decision
before it proceeds at all.

## Mandatory gates (requirement 4)

`gates.py`'s `evaluate_all_gates` runs eight of the nine; the ninth
(`paper_claims_link_evidence`) runs after the Markdown draft is rendered,
against the actual rendered text:

1. `claim_provenance` — every claim's `source_id` resolves to a source with a non-empty `source_checksum`.
2. `null_prediction` — every hypothesis has one.
3. `falsification_criterion` — every experiment plan has one.
4. `metric_units_and_families` — every declared/reported metric has a unit (and, on the plan, a feature_family).
5. `dataset_checksum` — every empirical execution has a dataset checksum and output checksums.
6. `locked_holdout` — every predictive experiment has `held_out_split_locked: true`.
7. `synthetic_not_promoted` — no validation report re-labels a synthetic execution's experiment as empirical.
8. `theory_contradictions_preserved` — every theory-declared contradictory-evidence id still resolves to a known claim.
9. `paper_claims_link_evidence` — every `- [ID] ...` bullet the rendered paper draft emits cites an id this compiler actually loaded.

Each gate result is `{"passed": bool, "violations": [...]}` under the
top-level `gate_results` key; a failing gate never silently degrades to a
warning (fail-closed — an empty violations list is the only pass signal).

## Forbidden-language policy (requirement 7)

`guardrails.find_forbidden_phrases` matches (case-insensitively) the
exact phrases *"proved consciousness"*, *"confirmed liberation"*,
*"demonstrated quantum coherence"* and their present-tense variants.
`guardrails.contains_causal_language` flags any `caus(e|ed|es|ing|ation|al)`
word. `render_markdown.check_unsupported_promotion` licenses either kind
of language **only** when the underlying record's `evidence_class ==
"formal"` **and** its human-review `decision == "approved"`; otherwise the
rendered text is annotated `[UNVERIFIED CLAIM -- ...]` and the violation
is recorded under `unsupported_promotion_violations`. Hypothesis
*statements* are checked for forbidden phrases but not causal language —
hypothesizing a causal relationship is ordinary, licensed pre-evidence
science; only a claim of *proven* causation needs the causal guard.

## Artifact ledger (requirement 5)

`ledger.build_artifact_ledger` produces one row per experiment plan:
`experiment_id`, `hypothesis_id`, `source_checksum` (from the first
resolvable claim source), `input_checksums`, `output_checksums`,
`software_commit`, `runtime_seconds`, `dependency_state`,
`scientific_status` (this orchestrator's own `evidence_class` —
`synthetic`/`proxy`/`empirical`/`formal`/`unknown`, where `formal`
requires an empirical, preregistered, held-out-locked experiment with a
completed PASS/FAIL null test), `reviewer_status`.

## Paper-ready Markdown draft (requirement 6)

`render_markdown.render_paper_draft` emits, in order: Research Question,
Literature Background, Hypotheses, Methods, Preregistered Predictions,
Results, Null Controls, Limitations, Alternative Explanations, Theory
Revision, Unresolved Questions, Claims Requiring Human Review. It opens
with an explicit blockquote stating the draft is not itself scientific
evidence. Every substantive line cites its backing id as `- [ID] ...` so
gate 9 can verify it.

## JSON requirements (requirement 8)

- No NaN/Infinity: rejected at load time (`evidence_loader.py`) and at
  the field level (`guardrails.safe_number`), including numeric strings
  and silent-overflow literals like `1e400`.
- Null for unavailable values: every normalizer degrades to `null`/an
  explicit fallback rather than guessing.
- Deterministic checksum: top-level `canonical_checksum`, a sha256 of
  `json.dumps(record, sort_keys=True, allow_nan=False)` computed after
  everything else and excluded from its own input.
- Schema version: `report_schema_version` and `input_contract_version`.
- Source manifest: `record_provenance.manifest_path` +
  `record_provenance.source_checksums[*]` (each explicitly
  `"checksum_scope": "local"` — a checksum is not independent
  validation).
- Evidence class: `claims[*].claim_status` (the registry's own vocabulary)
  and `artifact_ledger[*].scientific_status` (this orchestrator's
  derived classification), plus a summary count under
  `evidence_class_summary`.
- Human-review state: `reviewer_decisions` (as loaded) plus
  `human_review_summary` (hypotheses currently blocked on review, and
  every decision keyed by subject).

## Determinism

`compile_research_cycle(manifest_path, now=..., repo=...)` is a pure
function of its arguments and the contents of the files the manifest
points to — no network calls, no wall-clock reads unless `now` is
omitted, and no execution of anything it reads. Two compiles with the
same manifest, input files, and `now` value produce byte-identical JSON
(`canonical_checksum` included) and Markdown.

## CLI

```bash
python -m scripts.run_awareness_research_cycle \
    --manifest governance/awareness_research_cycle/manifest.json \
    --output-dir artifacts/awareness_research_cycle \
    --formats json,markdown,csv \
    --now 2026-01-01T00:00:00+00:00 --repo NeuroTopology-Sim
```

## This orchestrator does not certify scientific truth

`cycle_states`, `gate_results`, and the paper draft describe what the
supplied evidence records say and whether they satisfy this
orchestrator's structural gates — never an independent scientific
finding. `PAPER_DRAFT_READY` means "the evidence graph and human-review
records this orchestrator was given are internally consistent enough to
draft a paper," not "this hypothesis is true." Nothing in this package
runs a solver, a statistical test, or any other scientific computation;
it only reads, classifies, and reports on results computed elsewhere.
