# Research Plan Quality Rubric

Branch: `claude/research-plan-quality-rubric-20260910`, based on latest
`origin/main`. Owns exclusively: `tools/research_plan_quality/**`,
`scripts/audit_research_plan.py`, `tests/research_plan_quality/**`,
`docs/research/research_plan_quality_rubric.md`. Touches nothing in
existing claim-gate modules (`tools/ds005620_post_execution_controls/empirical_claim_gate.py`),
the Awareness Studio orchestrator, existing literature adapters,
Bayesian/topology code, `database/database.py`, CI/runner/data-loader
files, or any other agent's owned paths.

## What this is

A deterministic, rubric-centered evaluator for research plans and
preregistration manifests, inspired by PaperGym's rubric-scoring idea
(no external code copied or imported — every check is freshly and
independently implemented against this package's own `ResearchPlan`
input schema). It answers "how well-specified is this plan?", never
"is this plan's hypothesis true?".

**A high rubric score must never equal scientific confirmation.**
Every `PlanAuditResult` carries `evidence_class = "research_plan_audit"`
— a fixed, non-overridable label distinguishing this output from any
scientific-evidence record. The evaluator is a pure function of the
`ResearchPlan` the caller supplies: it never infers a missing field,
never fills in an unspecified method, and never fetches anything over
the network, downloads a paper corpus, or calls a model.

## The 20 rubric dimensions

`models.RUBRIC_DIMENSIONS` (asserted to be exactly 20 at import time):
`falsifiable_question`, `primary_endpoint`, `alternative_explanations`,
`source_quality_provenance`, `dataset_identity_checksum`,
`condition_label_validity`, `pairing_sample_size_adequacy`,
`power_or_precision_plan`, `multiplicity_correction`,
`null_model_specification`, `leakage_prevention`, `split_strategy`,
`preprocessing_lock`, `measurement_limitations`,
`compute_resource_budget`, `reproducibility`, `claim_calibration`,
`evidence_separation`, `replication_plan`, `ethical_privacy_constraints`.

Each has its own pure check function in `checks.py`
(`CHECKS_BY_DIMENSION`), asserted in `rubric.py` to cover exactly the
same 20 names — `evaluate_plan()` fails fast if the two ever drift.

## Criterion statuses and decision states

Each criterion resolves to one of four statuses (`models.CRITERION_STATUSES`):
`pass`, `warning`, `blocker`, `missing` (`missing` = the field was
entirely absent; `blocker` = present but invalid/contradictory — both
are "hard" and both land in `hard_blockers`, but only `missing` also
appears in `missing_fields`, so the two failure shapes stay
distinguishable in the output).

Overall status (`models.OVERALL_STATUSES`):
- **`BLOCKED`** — at least one hard blocker (`missing` or `blocker` status).
- **`NEEDS_REVISION`** — no hard blockers, but at least one warning.
- **`READY_FOR_EXECUTION`** — every dimension passes.

`overall_score` is the mean of each criterion's score (pass=1.0,
warning=0.5, blocker/missing=0.0) — purely descriptive/informational,
never itself a gate; the gate is `overall_status`.

## Key design decisions worth calling out

- **Multiplicity correction is conditional, not universal.** A plan
  declaring `number_of_planned_tests <= 1` legitimately passes this
  dimension with nothing else supplied — "not applicable" is a genuine
  pass state, not a loophole, since correcting for multiple comparisons
  only matters when there are multiple comparisons.
- **Claim calibration is evidence-class-aware.** Overclaiming/causal
  language (`"proves"`, `"causes"`, `"confirms"`, ...) is a **hard
  blocker** when `evidence_class_declared` is `synthetic` or `proxy` (a
  synthetic result can never license a causal claim about the real
  world) but only a **warning** when the evidence is `empirical` (still
  worth flagging, since even real data rarely "proves" anything, but not
  an automatic block).
- **Leakage prevention only blocks on an unaddressed *declared* risk.**
  If the plan declares no leakage risk at all and no controls, that is
  a warning (the risk was never assessed) — but a plan that explicitly
  names a leakage risk and supplies no control for it is a hard blocker,
  since that is a known, acknowledged gap rather than an unexamined one.
- **Sample-size adequacy is checked against the plan's own stated
  minimum**, never an externally imposed number — this evaluator has no
  domain-specific knowledge of what sample size a given effect size
  requires; it only checks the plan for **internal consistency** between
  its own `minimum_required_sample_size` (however that was derived, e.g.
  from the plan's own power analysis) and its declared `sample_size`.
- **Never fabricate a pass.** `test_evaluator_never_fabricates_a_value_for_missing_field`
  confirms that a maximally empty `ResearchPlan()` produces `BLOCKED`
  with every dimension reporting `missing`/`blocker`/`warning`, except
  the one dimension (`multiplicity_correction`) that can honestly pass
  on "zero planned tests declared."

## Output formats

`reporting.to_finite_json()` walks the full result and raises
`NonFiniteValueError` on any `NaN`/`Infinity` float before calling
`json.dumps(..., allow_nan=False)`. `reporting.to_markdown()` renders a
criterion table plus missing-fields/hard-blockers/warnings/
recommended-revisions sections, always naming `evidence_class` up front
so a reader never mistakes the audit for a scientific verdict.

## Test commands

```bash
PYTHONPATH=. python -m pytest tests/research_plan_quality -q     # 28 passed
python -m compileall -q tools/research_plan_quality scripts/audit_research_plan.py tests/research_plan_quality
python -m governance.validate                                     # 4/4 specs pass (baseline, unaffected)
git diff --cached --check                                         # no whitespace errors
```

No test opens a socket: `test_no_network_during_full_evaluation`
patches `socket.socket` to raise during a full plan evaluation;
`test_module_import_touches_no_network` confirms merely importing the
package touches nothing either. `test_no_heavy_import` runs in an
isolated subprocess and confirms none of
numpy/scipy/sklearn/mne/torch/pandas/requests end up loaded.
`test_isolated_subprocess_cli`/`test_isolated_subprocess_cli_blocked_exit_code`
drive `scripts/audit_research_plan.py` as a real child process,
including its exit-code contract (0 for non-`BLOCKED`, 1 for `BLOCKED`).

## Required test scenarios (all covered)

clean complete plan · missing provenance · ambiguous conditions ·
missing multiplicity · leakage · synthetic-only (evidence separation) ·
unsupported causal language · incomplete null model · low sample size ·
deterministic repeat · finite JSON · no-network · compileall ·
governance validation · `git diff --check` — see `test_rubric.py`.

## Known limitations

- This is a **structural/completeness** rubric, not a domain-expert
  statistical reviewer: e.g. `power_or_precision_plan` checks that a
  method/target-power/effect-size/alpha are all *stated*, not that the
  stated effect size is itself well-justified — that judgment call is
  out of scope for a deterministic, dependency-light evaluator.
- `claim_calibration`'s overclaim-phrase list is a fixed, small set of
  English phrases (`"proves"`, `"causes"`, `"confirms"`, ...) — it is a
  blunt lexical check, not an NLP claim-strength classifier; a plan
  could still overclaim in language this list doesn't catch, or (rarely)
  trip a phrase in a context where it's actually warranted, in which
  case the human reviewing the plan should treat the flag as a prompt to
  check, not a verdict to accept blindly.
- Author-overlap / dataset-ownership / cross-plan duplicate detection is
  out of scope here — this evaluator judges one plan in isolation, not a
  set of plans against each other.
- LLMs are explicitly not used anywhere in this implementation (per the
  task's safety requirement) — a future drafting assistant built on top
  of this rubric would call `evaluate_plan()` as a deterministic backend
  check on its own output, never the other way around.
