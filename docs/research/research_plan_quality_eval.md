# Research-plan rubric evaluation harness

Status: implemented and tested offline on ten synthetic fixtures. This harness
tests how the existing 20-dimension rubric (`tools/research_plan_quality`)
behaves on versioned fixtures, including leakage resistance. It does not
measure criterion leakage, human agreement, or generalisation. A rubric score
is not scientific confirmation, preregistration, or evidence that a hypothesis
is true.

Package: `tools/research_plan_quality_eval/`. Tests: `tests/research_plan_quality_eval/`.
Fixtures: `tools/research_plan_quality_eval/fixtures/v1/`.

The rubric itself is unchanged. The harness imports it read-only, and
`tools/research_cycle_preflight` is untouched.

## Primary-source check (PaperGym)

| Item | What was verified | Method |
|---|---|---|
| Canonical repository | `https://github.com/ZJU-REAL/PaperGym`, licence MIT, `Copyright (c) 2026 REAL Lab` | fetched the repository page and its `LICENSE` file |
| Paper identity | Title "PaperGym: Rubric-Centered Evolution for Research-Plan Generation", arXiv `2608.31119`, year 2026 | taken from the repository README citation metadata |
| Paper version and abstract | **Not verified.** The arXiv abstract page, Hugging Face, and the project site did not resolve from this environment | fetch attempts failed (DNS) |
| Model and dataset licence | Not stated on the repository page. Hugging Face pages were not reachable | none assumed |
| Leakage figure | The repository chart alt text reports 3.73% for PaperGym-20k. Not independently verified, not used | fetched README |

Nothing from PaperGym was copied, imported, or used. No code, corpus, model, or
reported figure is included.

Ideas considered safe to emulate, reimplemented independently here:

- **Keep targets out of the evaluator's input.** Label and answer-key data sit in a separate file that the evaluation path never opens.
- **Define every leakage measure and its denominator.** Report counts and an explicitly labelled fraction. No headline rate.

Ideas not emulated: LLM-judged criterion leakage (PaperGym's detector asks a
model whether each rubric can be inferred from a question), RL or
self-distillation training, win-rate comparisons, and any reported PaperGym figure.

## Fixture set (v1)

- Ten synthetic plans, `fx-v1-P01` to `fx-v1-P10`, in eight source/project/topic groups.
- Development role (`development`): P01–P05, groups A–D.
- Held-out role (`locked_internal_validation`, the vocabulary from `benchmarks/split_policy.py`): P06–P10, groups E–H.
- `manifest.json` records the schema, fixture-set id and version, the rubric
  dimension and source hashes, the label file hash, and for each plan its
  group, split, and SHA-256.
- `labels.json` holds per-plan expectations and adjudication metadata:
  `synthetic_author_expectation`, `independent: false`. The evaluator never reads it.
- Within group A, P01 and P02 are near-duplicates (Jaccard 0.774, below the
  threshold). P07 and P08 in group F share the same question and primary
  endpoint (Jaccard 1.0) and differ in sample size, alpha, and code version.
  Both pairs are within a single split, so they are not leakage.

Expectations were written from the rubric's documented rules, then compared to
the rubric's output. Two plans first failed `pairing_sample_size_adequacy` because
their pairing strings were outside the rubric's vocabulary
(`paired`, `unpaired`, `within_subject`, `between_subject`). I corrected those
two fixture values. The rubric code was not changed.

## Split definition

- Unit: `group_id` (source / project / topic). Whole groups are assigned to one
  role, and `check_group_integrity` rejects any group that spans two roles.
- The shipped split uses explicit assignment recorded in the manifest.
  `assign_group_splits` provides a deterministic salted assignment for future
  fixture sets, and it is tested.
- `require_sufficient` rejects an empty set, a missing role, or a role with fewer
  than 3 plans or 2 groups.

## Duplicate detection

Three reason codes, computed across all record pairs:

| Code | Rule |
|---|---|
| `exact_content_match` | identical canonical plan content, excluding `plan_id` |
| `normalized_text_match` | identical text after NFKC, casefold, and word-character normalisation of the four free-text fields |
| `near_duplicate_shingle_jaccard` | word-3-shingle Jaccard of question plus primary endpoint, at or above 0.85 |

Only cross-split pairs count as leakage. Within-split pairs are reported
separately. The held-out fraction is labelled
`held-out plans with a lexical cross-split duplicate; not a criterion-leakage rate`.

## Isolation

- Each stage takes the verified manifest, not records. The development stage
  loads only development plan files, and the held-out stage loads only held-out
  plan files. No record-list entry point accepts held-out plans.
- The split definition is the set of each fixture's id, group, role, and plan
  SHA-256. Its digest is pinned in `harness.py` (`PINNED_SPLIT_DEFINITION_SHA256`).
  A run whose definition differs is refused with `ManifestError`. A deliberate split or
  plan change needs a reviewed re-pin. Otherwise the run must declare
  `--allow-unpinned-split`, and the report then records `split_definition_pinned: false`.
- Held-out evaluation runs only against a frozen development result. It checks
  the configuration fingerprint and the split definition digest, and it reproduces
  the development outcomes from the plan files. A result that does not reproduce is
  refused. The frozen result is still process-local, so single-use access to held-out
  outcomes is not enforced here.
- The configuration covers the rubric source hash, dimension hash, duplicate
  threshold, shingle size, normalisation version, and minimum split sizes. Any change
  to the rubric source invalidates the manifest until labels are re-authored.
- Tests cover the reproduced attacks: a forged frozen stage, a reassigned group, and
  a held-out plan edited and re-hashed. They also cover the loader's role filter and
  the CLI exit code. Labels remain single-author expectations, not ground truth.

## Running

```
PYTHONPATH=. python -m tools.research_plan_quality_eval --json-out report.json
PYTHONPATH=. python -m pytest tests/research_plan_quality_eval -q
```

The report records the fixture hashes, rubric identity, split definition,
duplicate results, outcomes, consistency with the synthetic expectations,
`not_measured`, and `limitations`. For held-out fixtures the consistency entry
reports a mismatch without the expected values, so held-out labels never reach the
report. It is strict finite JSON with sorted keys and no timestamps.

## Limitations

- Fixtures are synthetic and were written by one person. They are not drawn from real plans.
- Labels are single-author expectations. Agreement with them is not human agreement and not ground truth.
- Only lexical duplicate signals are implemented. Semantic paraphrase leakage and criterion inferability are not measured.
- The rubric is structural. It does not judge domain soundness, statistical validity, or whether a hypothesis is true.
- Ten plans in eight groups cannot support any generalisation estimate.
- The threshold (0.85) and shingle size (3) were set by inspection, not calibrated on labelled duplicates.
- No LLM-judged leakage detection is implemented, and no leakage rate is reported.

## Needs human or empirical evaluation

- Independent adjudication of a real plan corpus by at least two raters, with
  agreement statistics. The current labels cannot provide this.
- Calibration of the duplicate threshold against labelled duplicate and
  non-duplicate pairs, with a sensitivity analysis.
- A criterion-leakage measure with a stated definition, judge, and
  denominator, validated against human judgements before any rate is reported.
- Any statement about whether rubric scores predict plan quality or outcomes.
