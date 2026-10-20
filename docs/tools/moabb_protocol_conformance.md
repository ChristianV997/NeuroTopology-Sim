# MOABB Protocol Conformance (offline)

Status: **implemented**. This package turns already-available MOABB candidate
metadata or local fixtures into a transparent **benchmark-protocol manifest**
and validates that manifest for protocol conformance only.

It does **not**:

- download datasets or call `moabb` / `get_data`
- install or import MOABB or MNE at runtime
- create a second dataset registry, provenance system, or evidence vocabulary
- make benchmark-execution, local-data-presence, or scientific-validation claims

Owned paths:

- `tools/moabb_protocol_conformance/`
- `tests/tools/moabb_protocol_conformance/`
- `docs/tools/moabb_protocol_conformance.md`

Read-only reuse: `dataset_importers.moabb_importer` and
`DatasetCandidateRecordV1`.

## Upstream references

| Software | Source | License | Version observed | Mode |
|---|---|---|---|---|
| MOABB | https://github.com/NeuroTechX/moabb | BSD-3-Clause ([LICENSE](https://github.com/NeuroTechX/moabb/blob/master/LICENSE), pyproject `BSD-3-Clause`) | not installed; `develop` tip inspected 2026-10-16 | reference + split-policy name emulation |
| MNE-Python | https://github.com/mne-tools/mne-python | BSD-3-Clause | not installed; referenced because MOABB lists `mne>=1.13` | reference only |
| In-tree importer | `dataset_importers/` | repo license | as on `origin/main` | read-only reuse |

REA / PaperGym / AutoResearch / OpenResearch are **not** runtime dependencies.

## Manifest fields

Dataset side (declared vs unknown):

- dataset identifier, task/paradigm, modality
- subjects / sessions (counts or ids only when supplied)
- channels (count/names only when supplied)
- event/label mapping source + labels (never invented)
- sampling metadata (only when supplied)
- license / access evidence (unknown preserved; conflicting blocked)
- local availability stays `unknown` unless explicitly supplied

`trust: verified` means only that a non-empty value was explicitly supplied
and was not found internally conflicting by this metadata check. It is not
independent source verification. A manifest does not prove data access, data
use rights, participant/cohort identity, or scientific validity; license and
access values are declarations for review, not legal clearance. The tool does
not access a MOABB dataset or verify any source catalog at runtime.

Manifest output is deterministic for identical inputs when callers either
omit `created_at` (serialized as `null`) or provide the same explicit
timestamp. No wall-clock timestamp is silently injected.

Protocol side (required):

- `protocol_version`
- `unit_of_analysis` ∈ {subject, session, recording, trial, window}
- `split_policy` ∈ known MOABB-inspired policies (see schema)
- `evaluation_metric` (not `unspecified`)
- `exclusions` list (explicit, may be empty)

## Subject leakage

- `random_trial_split` → **failed** (can place the same participant in train/test)
- `custom_subject_holdout` with overlapping train/test subject ids → **failed**
- missing custom holdout lists → **incomplete**
- within-subject policies with `unit_of_analysis=subject` → **inconclusive**
- `cross_subject_leave_one_out` → subject-blocked **ok**

## CLI

```bash
python -m tools.moabb_protocol_conformance \
  --moabb-fixture tools/moabb_protocol_conformance/fixtures/moabb_metadata_fixture.json \
  --protocol-json tools/moabb_protocol_conformance/fixtures/protocol_conforming.json \
  --output /tmp/moabb_protocol_manifest.json
```

Exit code `0` only when conformance status is `conforming`.

## Result semantics

`evidence_class = protocol_conformance_only`.

Statuses: `conforming` | `incomplete` | `inconclusive` | `failed` | `blocked`.

Engineering integrity is not empirical or biological evidence.
