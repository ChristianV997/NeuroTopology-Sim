# Independent audit: report-language, source-pack, and provenance-join PRs

Audit date: 2026-10-17 (updated after report-firewall remediation). Scope: PRs #390, #391, and #392 against the live remote default branch. This is an independent static review of PR diffs, changed-file lists, test sources, docs, focused local fixture tests, and available GitHub Actions status/logs. No participant data was inspected; no harvested content was executed or downloaded; no package was installed; no GitHub review comment or merge was made.

## Decision

HOLD. Preserve HOLD / SYNTHETIC_ONLY. #390's report-language findings listed below are resolved on its current head, but its latest Required Checks run is red for the same Awareness Studio failures present on live main. PRs #391 and #392 remain open drafts with unresolved P2 findings. None of the tools establishes truth, data rights, source authenticity, cohort identity, model correctness, or scientific validation. Hash/checksum agreement is internal byte/serialization consistency only.

Live main and PR heads:

| PR | State | GitHub-reported base SHA | Head branch | Head SHA |
| --- | --- | --- | --- | --- |
| #390 | Open, non-draft, unmerged | 19c3203573082f8bc41f7da226b52dc20a49fdb0 | batch3/codex-d-report-firewall | e7fe8252c3a7a9dbd675b324691de803d7d194b6 |
| #391 | Open, draft, unmerged | 3f3fe8593303184cb88eef056c1322f3d4e57a16 | batch1/hermes-a-safe-source-harvest | 6b48bae73430626f1b09c7863954f728b9b48fa9 |
| #392 | Open, draft, unmerged | 3f3fe8593303184cb88eef056c1322f3d4e57a16 | batch3/codex-c-provenance-join | e7919194823ce28a4ce0074ba723d288cddeb58e |

Live origin/main was re-verified at 19c3203573082f8bc41f7da226b52dc20a49fdb0. The #391/#392 base SHAs above remain their last GitHub-reported base snapshots; neither branch has been updated to the live main tip. #390's remediation branch includes a normal merge of live main; no history was rewritten.

## Current CI

The latest #390 Required Checks run is [39008661251](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39008661251): core-tests passed and awareness-tests failed. Separate ontology-claim-language [39008661223](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39008661223) and smoke [39008661284](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39008661284) checks passed. The failure is the same three tests and observed failure modes present on live main, not a report-firewall test failure. Current live main run [39001665754](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39001665754) has awareness-tests red and core-tests green. Earlier #391/#392 Required Checks runs remain red:

| PR | Required Checks run | Result |
| --- | --- | --- |
| #390 current head | [39008661251](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39008661251) | awareness-tests failed; core-tests passed |
| live main | [39001665754](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39001665754) | awareness-tests failed; core-tests passed |
| #391 | [38972226639](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/38972226639) | Failed |
| #392 | [38972195283](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/38972195283) | Failed |

Direct logs for both live main and #390 confirm the same three failures in `tests/research_cycle/test_registered_execution.py`: `test_registered_execution_persists_actual_artifacts_and_review` and `test_local_literature_links_to_experiment_and_execution` receive `EXECUTION_FAILED` rather than the expected `ENGINEERING_EXECUTION_COMPLETE`; `test_planning_does_not_execute_and_authorized_repeat_resumes` raises `KeyError: resumed`. The awareness-tests job reports 3 failed, 413 passed, and 1 skipped. These test paths are outside the three audited PRs' changed-file sets. Agent B's PR #422 (head `93c69ffea1df976ac86511531304360d876fda32`) adds an Awareness Studio runtime dependency and has green `awareness-tests`, `core-tests`, and Python 3.11/3.12 Awareness checks; its Docker build workflow currently has two failed image jobs, and it is not merged into live main. Therefore it does not yet clear #390's live CI blocker. Do not describe the PR as CI-green or merge-ready until required checks rerun green after the shared fix is integrated.

Focused #390 regression tests were independently run after remediation: 28 `unittest` tests pass on Python 3.12.14 and Python 3.14.7. Both versions compile the checker, CLI, and focused tests. The explicit-fixture CLI accepted selected local fixtures; traversal returned its structured input error. Existing claim checks were run only against selected local fixtures: the claim guardrail reported zero hits and the ontology language validator scanned four fixture files with zero violations. Full governance validation could not run locally because PyYAML is unavailable; no dependencies were installed. No current focused-test rerun was made for #391 or #392 in this remediation pass.

## Findings (severity-ranked)

### P2 — #392 coalesces distinct source identifier fields into one untyped join namespace

In tools/batch3_provenance_join/auditor.py, _REFERENCE_KEYS (lines 40–43), _source_ids (913–923), _source_ids_from_record (1161–1164), and the source_catalog membership check (1002–1004) collapse source_id, source_snapshot_id, source_manifest_id, snapshot_id, dataset_identifier, and dataset_id into raw strings. Source-manifest dataset identifiers and SourceSnapshot snapshot IDs are distinct contract fields; SourceSnapshot metadata is an untyped mapping. A coincidental equal string can therefore satisfy a reference and suppress unresolved_source_reference without a schema-defined typed relation. This conflicts with the docs’ claim that missing joins remain unresolved rather than inferred.

Recommendation: define schema-specific typed join keys and explicit allowed edges; report ambiguous/untyped references as unverifiable. Add a fixture where unrelated identifier types collide and assert that it does not resolve.

### P2 — #392 silently skips declared but unclassified origins

The current-main EmpiricalSourceManifest accepts empirical_local, synthetic_demo, external_solver, and unavailable. The auditor reports source_origin_unverifiable only when origin is absent (auditor.py:936–938). _declared_origin_class (1167–1174) maps only synthetic and empirical spellings; external_solver, unavailable, and unknown strings return None, and source-mode comparison is skipped when that happens. Thus a present but unclassified origin is not labeled unverifiable.

Recommendation: validate the origin vocabulary and emit an explicit unresolved/unverifiable finding for allowed origins that cannot be compared, as well as invalid values. Do not interpret silence as agreement.

### P2 — #391 pack-level reuse status ignores documentation-copy scope

tools/public_repo_harvest/source_pack.py accepts can_copy_docs in the license record, but explicit_copy_gate (305–318) requires can_copy_code only. The normalized license evaluation omits can_copy_docs and emits a single reuse_status (330); pack_static_source copies selected safe text files, including Markdown, and attaches that single status (971–973). A caller can supply can_copy_code=true and can_copy_docs=false and still get reuse_status=human_reviewed_compatible for a mixed code/documentation pack.

Recommendation: make reuse decisions file/content-scope aware or keep mixed packs blocked unless every selected content class has an explicit compatible review. The positive status is caller-supplied metadata, not independently verified legal clearance. The existing scanner correctly leaves unknown/conflicting claims blocked and a likely-license hint alone does not authorize copying; this finding concerns the positive status scope.

### Resolved on #390 head e7fe825 — P2 negation in a separate compound clause suppressed assertions

This was reproduced before the fix with `The analysis is not preregistered and demonstrates a causal mechanism.` A later comma-splice fixture also reproduced suppression: `The result was not independently replicated, the findings demonstrate a causal mechanism.` The current checker splits simple punctuation, coordinating conjunctions, and comma boundaries before a bounded set of common clause subjects, outside detected quote spans. Tests `test_negation_in_prior_compound_clause_does_not_suppress_positive_claim`, `test_negation_does_not_suppress_assertion_after_comma_clause_boundary`, and `test_multiple_assertive_claims_in_one_sentence_are_checked` now prove the positive claims remain warnings while explicit negations stay unflagged.

This is a deterministic heuristic, not grammatical analysis; unrecognized clause forms can still be missed or over-reported. Findings remain warning-only and require human review.

### Resolved on #390 head e7fe825 — P2 unrelated validation metadata excused scientific_status=VALIDATED

The status rule now emits `AMBIGUOUS_VALIDATION_STATUS` for validated status values under recognized status keys without allowing unrelated `validation_scope`, `validated_object`, or `validation_target` fields to suppress it. `test_scientific_validated_is_not_excused_by_software_scope_metadata` verifies the nested JSON path `$/report/scientific_status` with `validation_scope: software`. The checker still emits no status result of its own and never promotes scientific claims.

### Resolved on #390 head e7fe825 — P3 indented code and straight single-quoted spans were scanned

The Markdown reader now preserves leading whitespace when skipping four-space/tab-indented code; quote filtering covers straight single quotes in addition to double/curly quotes and backticks. `test_fenced_and_indented_markdown_code_are_not_scanned`, `test_straight_single_quoted_span_is_not_scanned`, and `test_quoted_negation_or_caution_does_not_suppress_unquoted_claim` cover false-positive and false-negative cases. Single-quote pairing remains heuristic for apostrophes, unmatched quotes, and nested spans; these contexts can still need human review.

### P3 — #392 documentation could state non-scientific/non-rights limits more explicitly

The docs say the audit does not decide whether results are true and is not scientific validation (docs/tools/batch3_provenance_join.md:3–6, 85–88). They also disclose missing license/checksum schemas. They do not explicitly say that structural lineage does not establish data rights, cohort identity, or model correctness. Add those as explicit limitations so “CLEAN” cannot be mistaken for any of them.

### P3 — #392 file-open race is detected after open, not prevented at open

auditor.py:_read_stable_file (147–170) performs lstat and then Path.open("rb"); fstat detects many replacements before bytes are read, but the open itself follows a replacement symlink and could block or have side effects if a regular file is swapped for a special file between checks. If concurrent adversarial mutation is in scope, use a no-follow regular-file open where supported and add a race-focused test. This is a hardening note; the static path-resolution checks otherwise reject traversal, links, and out-of-root references.

## Security, provenance, and scientific semantics

- #390 only reads explicitly selected Markdown/JSON under a bounded root; it rejects traversal and tested symlink escapes, produces warning findings with file/location/rule/recommendation, and does not modify reports. Normal JSON Pointer escaping is used. Its quote, negation, and Markdown-context filters remain heuristic, as detailed above.
- #391 enforces selected relative paths; per-file, total, depth, count, archive, compression, and output bounds; rejects traversal, ambiguous/case-colliding paths, symlinks/hardlinks and archive special files. It reads source bytes without importing, building, installing, or executing them. The output marks URL/commit/date as caller_supplied_not_verified_offline. Unknown/missing/conflicting license input remains blocked. Secret detection is heuristic; inspect packs before sharing.
- #392 uses exact serialized-hash rules for ledger, simulation lineage, EvidenceBundle IDs, and raw manifested artifacts where those contracts define scope. It explicitly leaves SourceSnapshot.source_sha256, RunRecord.input.source_sha256, source_manifest extensions, and RunRecordLink.run_record_sha256 unverified when scopes are undocumented. It labels missing producers/references unresolved and hardcodes scientific_validation=false. These are good boundaries, subject to the identifier/origin findings.
- No report checker, source pack, hash chain, or structural join proves source authenticity, participant/cohort identity, rights to data/code, software/model correctness, causation, mechanism, biological validity, or a scientific result.

## Paths, overlap, and order

Changed paths are disjoint and non-duplicative:

- #390: docs/tools/batch3_report_firewall.md; scripts/check_batch3_report_language.py; tests/tools/batch3_report_firewall/ (fixture and test files); tools/batch3_report_firewall/ (package and checker).
- #391: docs/public_repo_harvest_static_source_pack.md; tests/tools/test_public_repo_harvest_source_pack.py; tools/public_repo_harvest/{external_systems_scorecard.py,license_scanner.py,pattern_classifier.py,source_pack.py}.
- #392: docs/tools/batch3_provenance_join.md; scripts/run_batch3_provenance_join.py; tests/tools/batch3_provenance_join/; tools/batch3_provenance_join/.

There are no file conflicts among these three PRs. #390 is independent. #391 emits a new PublicRepoSourcePack.v1 manifest; #392’s classifier only recognizes existing current-main schemas and does not ingest that new source-pack manifest or its license evaluation. They can be reviewed independently, but no integrated source-pack-to-provenance join exists. If that integration is desired, add an explicit adapter/schema contract in a separate change rather than treating the pack as already joined.

## Disposition

Keep #390 open but not merge-ready until its Required Checks rerun green after the shared Awareness Studio fix reaches main; the four report-firewall defects above are fixed on its current head and do not clear CI or scientific gates. Keep #391 and #392 open as drafts pending their unresolved P2 findings. Do not merge based on core-tests alone or interpret any heuristic warning/absence, source-pack metadata, or structural join as truth, legal clearance, or scientific validation. Maintain HOLD / SYNTHETIC_ONLY. No scientific claim is validated by this audit.
