# Source-mining/evidence boundary integration tests

This isolated test package bridges the current `tools.public_repo_harvest` vocabulary to `tools.evidence_promotion_gate`; it adds no harvester, registry, provenance schema, research loop, or claim-state machine. Tests use temporary JSON fixture artifacts only and do not access the network, datasets, or harvested code.

## Contracts exercised

- `tools.public_repo_harvest.schema`: `SourceRepo`, `CandidateRepo`, and `LicenseCompatibilityRecord`; unknown licenses default to `license_status=unknown`, `compatibility_status=manual_review_required`, `can_copy_code=False`, and manual review required.
- `tools.evidence_promotion_gate.adapters`: local JSON classification/loading, malformed JSON reporting, extracted fields, case fingerprints, and read-only case discovery.
- `tools.evidence_promotion_gate.evaluator.evaluate_case`: finite promotion decision vocabulary, `scientific_pass=False`, non-empirical allowed classes, explicit license/cohort declarations for limited descriptive review, and fixture/synthetic acquisition held synthetic-only; `scientific_eligibility` is true only for the descriptive-review decision. Its claim path invokes `tools.research_claim_gate.gate.evaluate_claim`.

The source-pack and dataset metadata structures used here are test-only compatibility fixtures, not claimed production schemas. A hash/checksum proves only that bytes match a recorded digest; it does not prove source identity, license entitlement, cohort correctness, biological validity, or empirical truth. Public source behavior is not treated as scientific evidence.

## Compatibility assumptions and limits

- The main-branch harvest dataclasses do not define source-pack file hashes or source-identity resolution. The promotion adapter does not recognize `source_pack` as a dedicated artifact kind; these fixtures should remain non-promotable until a separately reviewed adapter contract exists.
- `public_repo_harvest.validator` checks required generated output files, not the semantic validity of source-pack file hashes. The malformed-JSON case is rejected by the promotion loader; a tampered hash field is verified not to become scientific support, but there is no current hash-semantic validator to assert rejection by. Do not interpret this suite as hash-chain verification.
- The promotion evaluator blocks explicit `empirical` declarations. For `descriptive_empirical` review eligibility it requires explicit `license_status="compatible"`, `cohort_status="consistent"`, and `cohort_discrepancy=false` declarations (top-level or under `dataset_metadata`). Missing, unknown, incompatible, malformed, or conflicting values hold the case inconclusive. This only evaluates declared metadata; it does not establish legal permission, dataset identity, cohort correctness, or scientific validity. Engineering-only metadata remains reportable without these data-readiness declarations.
- Source-code analysis, literature, fixtures, and dry-run inputs are tested as non-empirical types; no external implementation is imported or run.

## Offline command

In a full repo test environment: `pytest -q tests/source_mining_integration`.

A minimal offline environment lacking root test dependencies can isolate this suite with: `uv run --offline --with pytest pytest --override-ini='required_plugins=' -o addopts='' --confcutdir=tests/source_mining_integration -q tests/source_mining_integration`.
