# Literature Evidence Adapter

Branch: `claude/literature-evidence-adapter`, based on latest
`origin/main`. Owns exclusively: `tools/literature_evidence/**`,
`scripts/validate_literature_evidence.py`, `tests/literature_evidence/**`,
`docs/awareness_studio/literature_evidence.md`. Touches nothing in the
Awareness Studio orchestrator, the research-cycle ledger, `tools/research_claim_gate/**`,
`tools/awareness_studio_research/**` (a separate, already-merged sibling
package with a similar aim — read for context only, never imported
from), dataset acquisition, simulation code, CI workflows, or any
protected user file.

## What this is

A local-first adapter that records literature **source identity**
separately from **claims made about a source**, with an immutable,
append-only audit history. It never adjudicates scientific truth and,
structurally, **cannot** promote a claim into confirmed empirical
evidence — the schema itself has no "empirical"/"confirmed" value for
`claim_kind` or `evidence_class` to be set to (see `models.py`). Every
claim defaults to, and can only ever be, `hypothesis` or
`review_required`.

## Schema (`LiteratureEvidence.v1`)

`LiteratureRecord` (source identity — requirement 1): `identifier`
(DOI/arXiv/ISBN/URL/other) + `identifier_type`, `title`, `authors`,
`venue`, `publication_type`, `publication_date`, `source_url`,
`retrieval_timestamp`, `content_checksum`, `excerpt_hash`,
`citation_relations`, `review_status`, `evidence_class`, plus a
`version`/`status`/`superseded_by` lifecycle. `ClaimRecord` (requirement
2) references a `source_id` but is a wholly separate record — a source
record has no claim-text field, and a claim record has no citation
metadata field. `SourceSnapshot` (requirement 3) is either
`full_local_snapshot` (a locally captured file this package can
checksum) or `metadata_only` (no local content at all, explicitly
supported, not treated as an error).

## Validation states (requirement 5)

`validation.validate_record()` returns one of five states, checked in
this priority order (documented in the module so it's clear which check
"owns" a rejection when a record fails more than one):

1. `rejected_missing_identity` — identifier absent entirely.
2. `rejected_fabricated_identifier` — identifier present but
   structurally/checksum-invalid for its declared type. DOI/arXiv use a
   format regex; **ISBN uses a real ISBN-10/13 check-digit computation**
   (`identifiers.py`), which catches a well-formed-*looking* but
   fabricated ISBN the same way a truncated-then-padded git commit hash
   was caught elsewhere in this session — a plausible-looking identifier
   is not the same as a real one.
3. `rejected_invalid_checksum` — a declared `content_checksum`/
   `excerpt_hash` is not a well-formed sha256 hex digest, or a
   `full_local_snapshot`'s declared checksum does not match the
   **actual, freshly computed** checksum of the file at its `local_path`
   (a real streaming sha256 read, not a stub).
4. `rejected_unsupported_publication_status` — `publication_type` or
   `review_status` is not one of the recognized vocabularies.
5. `valid` — every check above passed.

This module never makes a network call to confirm an identifier
actually resolves to a real paper (that would require network access,
out of scope) — it only rejects what is checkable structurally/locally.

## Never automatically promote literature into empirical evidence (requirement 7)

`models.CLAIM_KINDS = {"hypothesis", "review_required"}` and
`models.EVIDENCE_CLASSES = {"hypothesis", "theoretical", "review_required", "proxy"}`
— neither set includes `"empirical"` or `"confirmed"`.
`ClaimRecord.__post_init__` raises `ValueError` if `claim_kind` is ever
anything else, so this is enforced at construction time, not just by
convention. Promoting a literature claim to empirical status, if it
ever happens, necessarily requires a separate system this package does
not implement — `test_claim_kind_can_never_be_empirical` and
`test_claim_kinds_and_evidence_classes_never_include_empirical` assert
this directly.

## Append-only store

`store.LiteratureEvidenceStore` is a JSONL event log, independently
implemented (no import of `tools/awareness_studio_research/store.py`,
a separate sibling package with a similar design). Every mutation
(`add_source`, `supersede_source`, `dispute_source`, `retract_source`,
`add_claim`, `mark_claim_review_required`, `add_snapshot`) appends
exactly one event, including an optional `reason` string for audit
context; re-adding an existing id raises `ImmutabilityError`. The
"current state" is a deterministic projection rebuilt by replaying the
log from position zero on every read.

## Network policy (requirement 4)

`network.py`'s `fetch_doi_metadata`/`fetch_arxiv_metadata` require
`allow_network=True` explicitly and raise `NetworkDisabledError`
otherwise. No importer, no CLI command (`scripts/validate_literature_evidence.py`),
and no default test path ever sets that flag.

## Test commands

```bash
PYTHONPATH=. python -m pytest tests/literature_evidence -q     # 36 passed
python -m compileall -q tools/literature_evidence scripts/validate_literature_evidence.py tests/literature_evidence
python -m governance.validate                                    # 4/4 specs pass (baseline, unaffected)
```

No test opens a socket: `test_no_network_during_full_ingest_cycle`
patches `socket.socket` to raise during a full validate+store cycle
across all three fixture publication types; `test_module_import_touches_no_network`
confirms merely importing the store module touches nothing.
`test_no_heavy_import` runs in an isolated subprocess and confirms none
of numpy/scipy/sklearn/mne/torch/pandas/requests load.

## Required test scenarios (all covered)

peer-reviewed paper · preprint · theory paper (ISBN identifier) ·
unresolved/fabricated identifier · missing source content
(metadata-only + a snapshot pointing at a nonexistent file) · finite
JSON (round-trip + NaN/Infinity rejection) · no-network (patched socket
+ import-time check) · deterministic repeatability (validation output
and event-log reads) · isolated-subprocess CLI (validate/ingest,
including the fabricated-identifier rejection exit code) — see
`test_literature_evidence.py`.

## Known limitations

- Identifier validation is structural/checksum-only — it cannot confirm
  a well-formed DOI/arXiv id actually resolves to a real paper (that
  would require network access, explicitly out of scope for this
  package's default behavior). A separate resolution step (e.g. this
  repository's `tools/awareness_studio_research/source_resolution.py`,
  not imported here) is the appropriate place for that check.
- `citation_relations` are caller-supplied references to other
  `source_id`s — this package does not itself discover citations from
  full text.
- Only `LiteratureRecord` and `ClaimRecord` have a full
  supersede/dispute/retract lifecycle; `SourceSnapshot` is currently
  append-only/single-version.
