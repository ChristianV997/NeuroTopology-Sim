# Independent audit: report-language, source-pack, and provenance-join PRs

Audit date: 2026-10-16. Scope: PRs #390, #391, and #392 against the live remote default branch. This is an independent static review of the PR diffs, changed-file lists, test sources, docs, PR-reported focused tests, and available GitHub Actions status/log summaries. No participant data was inspected; no harvested content was executed or downloaded; no package was installed; no GitHub comment or merge was made.

## Decision

HOLD. Preserve HOLD / SYNTHETIC_ONLY. All three PRs remain open drafts and have review findings below. None of the tools establishes truth, data rights, source authenticity, cohort identity, model correctness, or scientific validation. Hash/checksum agreement is internal byte/serialization consistency only.

Live main and PR heads:

| PR | State | Base SHA | Head branch | Head SHA |
| --- | --- | --- | --- | --- |
| #390 | Open, draft, unmerged | 3f3fe8593303184cb88eef056c1322f3d4e57a16 | batch3/codex-d-report-firewall | 2ea9a3b5bdb9c70844dce23b120b7589607fd6b0 |
| #391 | Open, draft, unmerged | 3f3fe8593303184cb88eef056c1322f3d4e57a16 | batch1/hermes-a-safe-source-harvest | 6b48bae73430626f1b09c7863954f728b9b48fa9 |
| #392 | Open, draft, unmerged | 3f3fe8593303184cb88eef056c1322f3d4e57a16 | batch3/codex-c-provenance-join | e7919194823ce28a4ce0074ba723d288cddeb58e |

Live main was verified at 3f3fe8593303184cb88eef056c1322f3d4e57a16 during this audit.

## Current CI

For each PR head, Ontology Claim Language and Smoke completed successfully. The core-tests job completed successfully; its isolated runner reported 9 files/batches passed with no failures or timeouts. Required Checks is red for all three heads:

| PR | Required Checks run | Result |
| --- | --- | --- |
| #390 | [38971290296](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/38971290296) | Failed |
| #391 | [38972226639](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/38972226639) | Failed |
| #392 | [38972195283](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/38972195283) | Failed |

The failure is the same three tests in tests/research_cycle/test_registered_execution.py: test_registered_execution_persists_actual_artifacts_and_review (EXECUTION_FAILED instead of ENGINEERING_ACTION_COMPLETE), test_planning_does_not_execute_and_authorized_repeat_resumes (KeyError: resumed), and test_local_literature_links_to_experiment_and_execution (EXECUTION_FAILED instead of ENGINEERING_ACTION_COMPLETE). The awareness-tests job reports 3 failed, 413 passed, and 1 skipped; core-tests passes. These test paths are outside all three PR changed-file sets. Their repetition across the heads suggests a shared failure, but this audit did not establish causation or compare against a separate main CI run.

Focused test results are reported in the PR descriptions, not independently rerun in this audit: #390 reports 20 unittest cases passing; #391 reports 16 passing/1 skipped; #392 reports 65 passing/1 skipped in its direct harness. The available CI job summaries do not establish that each of those focused suites ran in CI. #392 reports pytest and PyYAML unavailable in its local runtime. No dependencies were installed for this review.

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

### P2 — #390 a negation elsewhere in a compound clause can suppress an actual assertion

tools/batch3_report_firewall/checker.py uses _NEGATED_ASSERTION (57–61), a clause split limited to punctuation and “but” (113), and _is_negated_or_limited (201–203), which skips the whole clause if the negation regex finds any matching target within 100 characters. For example, “The analysis is not preregistered and demonstrates a causal mechanism” can be treated as wholly negated even though the causal assertion is positive. The causal language is then not reported.

Recommendation: constrain negation to the assertion it grammatically scopes; when uncertain, retain a warning for human review instead of suppressing the entire compound clause. Add mixed-negation regression fixtures.

### P2 — #390 scientific_status=VALIDATED can evade the status warning with an unrelated scope

In checker.py (285–288), any nonempty validation_scope, validated_object, or validation_target suppresses AMBIGUOUS_VALIDATION_STATUS for the bare value VALIDATED. Because scientific_status is among _STATUS_KEYS and metadata status fields are not rescanned as prose, a JSON object such as {\"scientific_status\":\"VALIDATED\",\"validation_scope\":\"software\"} gets no status finding. A software scope does not make an explicitly scientific VALIDATED status safe.

Recommendation: always flag VALIDATED under scientific_status, and only treat an explicit engineering scope as a reason to distinguish an engineering validation status when the field/value contract supports that interpretation. The checker itself still emits no scientific VALIDATED status and remains advisory.

### P3 — #390 Markdown exclusion misses indented code and straight single-quoted assertions

Fenced code and blockquotes are excluded by the parser and covered by fixtures. However, _markdown_paragraphs (388–400) calls raw.strip() before testing whether stripped starts with four spaces or a tab, so those indentation checks cannot succeed; standard indented code can be scanned as prose. _quote_spans (180–195) handles double quotes, curly quotes, and backticks but not straight single-quoted spans. These cases can create false-positive warnings, not automatic blocks. Add fixtures and preserve the human-review-only behavior.

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

Keep #390–#392 open as drafts pending the P2 findings and red Required Checks. Do not merge based on a clean core-tests job alone. Maintain HOLD / SYNTHETIC_ONLY. The structural and advisory outputs should not promote any scientific or legal status.
