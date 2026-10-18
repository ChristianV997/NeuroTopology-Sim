# Independent audit: report-language, source-pack, and provenance-join PRs

Audit date: 2026-10-18. This refresh rechecks live PR metadata, branch/base SHAs, changed paths, hosted CI, review state, and #390's focused local behavior. The #391/#392 source-code findings below were previously observed on older heads; their current source diffs were not re-reviewed in this refresh. No participant data was inspected; no harvested content was executed or downloaded; no package was installed; no GitHub review comment or merge was made.

## Decision

HOLD. Preserve HOLD / SYNTHETIC_ONLY. The four report-firewall regression behaviors covered by #390 are demonstrated by its current tests and the focused suite passes locally. This does not make the checker a truth detector or clear its red required CI. PRs #390 and #404 have failed Required Checks and no approving human review is recorded. Keep both open and do not merge.

The prior #391/#392 findings remain unresolved for audit purposes, but are historical observations—not assertions that the changed current heads still contain those defects. Their branches and PR states changed since the source review, so current behavior cannot be inferred from the old snapshots or from PR descriptions. None of these tools establishes truth, data rights, source authenticity, cohort identity, model correctness, or scientific validation. Hash/checksum agreement is internal byte/serialization consistency only.

Live main and PR refs verified on 2026-10-18:

| PR | Current state | Base SHA | Head branch | Head SHA |
| --- | --- | --- | --- | --- |
| #390 | Open, non-draft, unmerged | 19c3203573082f8bc41f7da226b52dc20a49fdb0 | batch3/codex-d-report-firewall | e7fe8252c3a7a9dbd675b324691de803d7d194b6 |
| #391 | Open, draft, unmerged | 19c3203573082f8bc41f7da226b52dc20a49fdb0 | batch1/hermes-a-safe-source-harvest | ffd24dbc9fe3e1695af1e8d656754f89c4e7f4aa |
| #392 | Open, non-draft, unmerged | 19c3203573082f8bc41f7da226b52dc20a49fdb0 | batch3/codex-c-provenance-join | bb02e885d38b473123645e0a1b31edbe2ad5ecf9 |
| #404 | Open, non-draft, unmerged | 19c3203573082f8bc41f7da226b52dc20a49fdb0 | batch3/codex-d-provenance-firewall-review | 6e06ba095fff21757f30a5016684ddb9d09be746 before this audit-document refresh |

The audit worktrees and remote refs were verified against https://github.com/ChristianV997/NeuroTopology-Sim. Live origin/main was 19c3203573082f8bc41f7da226b52dc20a49fdb0. The #404 row identifies the branch head before this document update; the resulting audit commit will have a new head.

## Hosted CI and review evidence

The latest Required Checks runs observed for the listed heads were:

| Ref | Required Checks | Core | Awareness |
| --- | --- | --- | --- |
| #390 head e7fe825 | [39008661251](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39008661251) | Passed | Failed |
| #404 pre-refresh head 6e06ba0 | [39008812408](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39008812408) | Passed | Failed |
| #391 head ffd24db | [39009196915](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39009196915) | Passed | Failed |
| #392 head bb02e88 | [39115730165](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39115730165) | Passed | Failed |
| live main 19c3203 | [39001665754](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39001665754) | Passed | Failed |

For #390, Ontology Claim Language [39008661223](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39008661223) and Smoke [39008661284](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39008661284) passed. For the pre-refresh #404 head, Ontology [39008812423](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39008812423) and Smoke [39008812442](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39008812442) passed. For #391, Ontology [39009196922](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39009196922) and Smoke [39009196945](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39009196945) passed. For #392's current head, Ontology [39115730115](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39115730115) and Smoke [39115730111](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39115730111) passed. These are successful subsets, not green Required Checks. The first audit-refresh commit 475734278e2220ee3908a2b90119250187497835 later completed Required Checks with core passed and Awareness failed ([39167270249](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39167270249)); its Ontology and Smoke checks passed ([39167270263](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39167270263), [39167270273](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39167270273)). Those results apply to that exact commit, not a subsequent documentation-only update.

Direct Awareness job logs for #390, pre-refresh #404, live main, and current #392 show the same three failures in tests/research_cycle/test_registered_execution.py: two tests receive EXECUTION_FAILED instead of ENGINEERING_EXECUTION_COMPLETE, and the resume test raises KeyError: resumed. The jobs reported 3 failed, 413 passed, and 1 skipped. This establishes the same failure modes on live main and the listed PR heads; it does not turn a failed required check green. #391's Required Checks also failed; its current source/tests were not independently re-run here.

Review submissions for #390 and #404 contain only Copilot quota-limit notices. Neither has inline review threads or an approving human review recorded. GitHub reports both PRs mergeable, but mergeable status is not approval or release readiness. The failed required check and missing approval evidence block an authorized merge.

## #390 behavior rechecked on current head

On 2026-10-18, the exact #390 head e7fe8252c3a7a9dbd675b324691de803d7d194b6 was tested with the bundled Python 3.12.14 runtime:

- python -m unittest discover -s tests/tools/batch3_report_firewall -p 'test_*.py' -v — 28 passed.
- python -m compileall -q tools/batch3_report_firewall scripts/check_batch3_report_language.py tests/tools/batch3_report_firewall — passed.
- git diff --check origin/main...HEAD — passed.
- The CLI help ran. Scanning the explicitly selected local assertions.md fixture emitted advisory findings and exited 0. Selecting a path that traverses outside the fixture root returned structured input_errors and exit 2.
- Tests cover no-network/no-execution behavior, deterministic output, bounded explicit selection, symlink escape, quotes, negation, code exclusions, JSON status paths, and false-positive safeguards.

The current required-check workflow does not demonstrate this focused suite in hosted CI: the core job passes an explicit allowlist of nine test files and omits tests/tools/batch3_report_firewall/test_checker.py, while Awareness runs pytest -q tests with working-directory apps/awareness_studio. Thus the 28-pass result above is local evidence only.

This refresh independently reran Python 3.12.14 only. The PR description reports an earlier Python 3.14.7 run; that version was not rerun during this refresh. No dataset, participant data, external report, or harvested content was used.

The specific regression tests passed: test_negation_in_prior_compound_clause_does_not_suppress_positive_claim, test_negation_does_not_suppress_assertion_after_comma_clause_boundary, test_multiple_assertive_claims_in_one_sentence_are_checked, test_scientific_validated_is_not_excused_by_software_scope_metadata, test_fenced_and_indented_markdown_code_are_not_scanned, and test_straight_single_quoted_span_is_not_scanned. The JSON status fixture checks the location $/report/scientific_status despite validation_scope: software.

Static inspection confirms the checker accepts only caller-selected Markdown/JSON paths below a bounded root, rejects traversal and symlinks, enforces file/count/total-size bounds, reads selected bytes, and returns findings to stdout. It does not rewrite reports. The CLI exposes advisory_only and review_recommended with warning findings; it does not emit scientific VALIDATED or any scientific verdict. Citation/evidence references are detected heuristically but are never opened or verified.

The compound-clause splitter uses simple punctuation, coordinating conjunctions, and selected comma-led boundaries; quote pairing and Markdown context handling are deterministic heuristics, not a grammar parser. Covered quoted, negated, fenced, and indented-code cases pass, but arbitrary grammar, malformed quotes, nested quotes, and unusual Markdown may still be missed or flagged. Findings are advisory requests for human review, not proof of misconduct, falsity, evidence, or scientific validity. The checker cannot replace the project's evidence gate.

## Historical findings on older #391/#392 heads — not cleared by this refresh

The following observations were recorded in an earlier static review against base 3f3fe8593303184cb88eef056c1322f3d4e57a16, #391 head 6b48bae73430626f1b09c7863954f728b9b48fa9, and #392 head e7919194823ce28a4ce0074ba723d288cddeb58e. Those are not the current bases/heads above. No claim is made here that the same code remains in the newer heads; each item remains unresolved until independently checked against the live PR diff and regression evidence.

- Historical P2, #391 license scope: the earlier source-pack snapshot appeared to gate mixed code/documentation reuse using can_copy_code while omitting can_copy_docs from the pack-level status. Recommendation at that time: make reuse decisions file/content-scope aware or keep mixed packs blocked unless each selected content class has an explicit compatible review. Caller-supplied license status is not legal clearance.
- Historical P2, #392 typed identifiers: the earlier join snapshot appeared to collapse source_id, source_snapshot_id, source_manifest_id, snapshot_id, dataset_identifier, and dataset_id into untyped strings. Recommendation: define schema-specific keys and allowed edges; collisions between identifier types should remain unverifiable.
- Historical P2, #392 origins: the earlier snapshot appeared to skip comparison for present but unclassified origins. Recommendation: validate the vocabulary and explicitly label unknown/uncomparable origins unverifiable.
- Historical P3, #392 limitations: the earlier docs did not explicitly say structural lineage does not establish data rights, cohort identity, or model correctness.
- Historical P3, #392 file opening: the earlier static review noted a possible lstat/open replacement race. This was a hardening observation, not a demonstrated exploit.

These are historical static observations, not reproduced runtime vulnerabilities. Current PR descriptions or author-reported tests do not clear them; current heads need a new source review. No legal conclusion is made.

## Current changed paths and integration relationship

Changed paths were refreshed from GitHub on 2026-10-18:

- #390: docs/tools/batch3_report_firewall.md; scripts/check_batch3_report_language.py; tests/tools/batch3_report_firewall/ (focused test and four fixture files); tools/batch3_report_firewall/ (__init__.py and checker.py).
- #391: docs/public_repo_harvest_static_source_pack.md; tests/tools/test_public_repo_harvest_source_pack.py; tools/public_repo_harvest/{external_systems_scorecard.py,license_scanner.py,pattern_classifier.py,source_pack.py}.
- #392: docs/tools/batch3_provenance_join.md; scripts/run_batch3_provenance_join.py; tests/tools/batch3_provenance_join/ (helpers and two test modules); tools/batch3_provenance_join/{__init__.py,auditor.py,models.py}.
- #404: docs/reviews/batch3_provenance_firewall_audit.md only.

The current changed-path lists are disjoint. #404 is an audit-document follow-up to #390 and must describe the exact checker head/evidence it reviews. #390 is path-independent of #391/#392. Disjoint paths alone do not establish semantic compatibility. An earlier review found no explicit source-pack-to-provenance-join adapter on the then-audited heads; that integration claim was not rechecked on the new #391/#392 heads. No merge order between #391 and #392 is certified here.

## Disposition

Keep #390 and #404 open and unmerged. #390 remains blocked by failed Required Checks and absent approval evidence. #404's pre-refresh Required Checks were also red; its updated documentation needs hosted checks and review on the resulting head. Do not merge based on mergeable=true or successful subsets.

Keep #391 open as a draft and #392 open, non-draft. Their prior P2/P3 findings remain audit-unresolved pending current-head review; this is not a conclusion that those defects persist. No PR in this audit is declared merge-ready. Maintain HOLD / SYNTHETIC_ONLY. No heuristic warning, source-pack metadata, lineage hash, or structural join validates a scientific claim, grants rights, or proves biological evidence.
