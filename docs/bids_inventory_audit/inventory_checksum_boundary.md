# Synthetic-only BIDS inventory and checksum boundary

Status: `HOLD`. Evidence class: `SYNTHETIC_ONLY`. Scope: `INVENTORY_LEVEL_ONLY_PENDING_AUTHORITATIVE_MANIFEST`.

Code: `shared/bids_inventory_audit/`. Tests: `tests/bids_inventory_audit/`.

This package works only on text, bytes, and mappings that the caller supplies. No function opens
a file, makes a network call, or runs a process. It never inspects real participant data, and
no dataset has been authorized for download or analysis.

## What it does not establish

- **Cohort identity.** An inventory lists participants and files. It does not show which subjects
  any analysis or publication used. `cohort_identity` is always `NOT_ESTABLISHED`.
- **Registration.** A checksum is not a preregistration. Every result carries
  `registration_status: UNREGISTERED_DRAFT`, `external_timestamp_created: false`, and
  `preregistration_claim: false`.
- **License resolution.** A conflict between sources remains a conflict. No source is preferred,
  and `resolved` and `adjudicated` are always `false`.
- **Scientific status.** `scientific_pass` is always `false`.

## Two concepts that stay separate

| Concept | Function | What it proves | What it does not prove |
|---|---|---|---|
| Payload integrity | `check_payload_digest` | The supplied bytes equal the recorded digest | Registration, timing, authorship, or analysis plan validity |
| Listing digest | `file_listing_digest` | A deterministic digest of a caller-supplied `(path, bytes)` listing | A dataset release, a cohort, or a registration |

The listing digest is read-only. It does not walk a directory. It is independent of entry order.
A path appearing twice, an unsafe path, or non-byte content produces no digest, so the call fails closed.

## Checksum outcomes

| Input | Outcome | Notes |
|---|---|---|
| Payload not bytes, or `None` | `PAYLOAD_MISSING` | Only `bytes` and `bytearray` are hashed |
| Empty bytes, any digest | `PAYLOAD_EMPTY` | Empty bytes are never a valid plan |
| Digest `None` or `""` | `DIGEST_MISSING` | Absence is not treated as a match |
| Digest equal to SHA-256 of empty bytes | `DIGEST_PLACEHOLDER` | Degenerate for a non-empty payload |
| Placeholder word (`TBD`, `todo`, `<sha256>`, and similar, any case) | `DIGEST_PLACEHOLDER` | |
| 64 identical characters | `DIGEST_PLACEHOLDER` | Filler, not a hash |
| Not exactly 64 lowercase hex, padded, prefixed, or not text | `DIGEST_MALFORMED` | Strict form only |
| Well-formed digest that matches | `PAYLOAD_INTEGRITY_VERIFIED` | Still `UNREGISTERED_DRAFT` |
| Well-formed digest that differs | `PAYLOAD_DIGEST_MISMATCH` | |

The recorded digest is never echoed into the output.

## Inventory checks

Subject cross-checks run only when a participants table is supplied. Without one, the result states
`cross_check: NOT_PERFORMED`.

- **Participants table** (`tsv.py`). Header must contain `participant_id`, or the parse fails closed.
  Malformed rows, invalid identifiers, and blank lines are reported with line numbers. A duplicated
  identifier is excluded entirely, because the table is ambiguous about it.
- **Paths** (`paths.py`). The BIDS entity grammar is applied to the subject-level layout. Unsafe
  paths are rejected. A backup or temporary copy (`.bak`, `.tmp`, `.old`, `.partial`, and others)
  is never a valid data file, so it cannot manufacture task coverage.
- **Subjects.** Files for subjects absent from the table are reported. Participants with no valid
  file are reported.
- **Duplicates.** Identical paths are reported. Different paths that claim the same BIDS entities
  are flagged and not resolved.
- **Tasks.** Expected tasks must be declared by the caller. The audit never infers them from observed
  files. Without a declaration it reports `EXPECTED_TASKS_NOT_DECLARED` and makes no completeness claim.
  With a declaration, it reports per-participant gaps (`MISSING_TASK_FOR_SUBJECT`), tasks absent for
  every participant (`TASK_ABSENT_FOR_ALL_SUBJECTS`), and observed tasks outside the set
  (`UNEXPECTED_TASK`). If no participants table is supplied, it reports only whether a declared task
  appears anywhere in the listing (`TASK_ABSENT_IN_LISTING`).

## License evidence

Two sources are read: a README's license lines, and a metadata mapping's license field. Only a closed
set of tokens is recognized (`CC0-1.0`, `CC-BY-4.0`, `CC-BY-SA-4.0`). Anything else stays unrecognized.

| State | Meaning |
|---|---|
| `UNKNOWN` | No evidence was supplied |
| `UNRESOLVED` | A source is unrecognized, has no license field, or has no statement |
| `CONFLICT_UNRESOLVED` | Sources, or one source, name different tokens |
| `SINGLE_SOURCE_NOT_ADJUDICATED` | One recognized token from one source |
| `AGREEMENT_NOT_ADJUDICATED` | Two or more sources agree on one token |

All states carry `resolved: false` and `selected_license: null`. Agreement is recorded, but it is not a
legal adjudication. In the synthetic fixture, a README naming CC-BY-4.0 and metadata naming CC0 produce
`CONFLICT_UNRESOLVED`, and the audit reports it as an error.

## Relation to the Round 6 statement

The scope string and status vocabulary mirror the Round 6 statement. This package is an independent
reimplementation. No Round 6 parser or checksum validator was found on `origin/main` or on any remote
ref, so there are no tests against Round 6 code, and nothing here has been checked against Round 6
outputs.

The existing `verify_plan_checksum` in `tools/data_access/approved_adapter/models.py` is a different
check. It hashes an acquisition plan dictionary. It does not produce `UNREGISTERED_DRAFT` and it does
not classify placeholders, so this package does not use it.

## Ownership

Open PRs #395 (`batch1/hermes-b-ds005620-manifest`) and #369 (`cursor/bids-adapter-provenance-96c3`)
own adjacent BIDS, NEMAR, and fixture paths. This branch touches none of them. The DS005620 metadata
fixtures in #395 were not opened.

## Unhandled cases

- BIDS coverage is a subset: no sidecar pairing, no `dataset_description.json` validation, no
  derivatives semantics, no session-level expectations.
- The extension is recorded as written. It is checked only for backup and temporary suffixes, not
  against the BIDS registry.
- The TSV reader is tab-separated with no quoting or escaping. The caller supplies decoded text, and
  encoding is not detected.
- Subject and task labels are case-sensitive. Unicode normalization is not performed.
- Duplicate content under different paths is not detected. Only entity signatures are compared.
- The license token table is closed. A newer license is reported as unresolved, not classified.
- An empty listing has a defined digest, but that digest has no meaning beyond "the empty listing".
- No size limits are applied to inputs.

## Running the tests

From the repository root:

```bash
python -m pytest tests/bids_inventory_audit -q
```

The fixtures under `tests/bids_inventory_audit/fixtures/` are labelled synthetic. They are not dataset
metadata.
