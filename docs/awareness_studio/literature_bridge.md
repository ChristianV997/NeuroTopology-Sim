# Awareness Studio Literature Bridge

Branch: `claude/awareness-studio-literature-bridge`, based on latest
`origin/main`. Owns exclusively:
`apps/awareness_studio/src/awareness_studio/literature_bridge/**`,
`apps/awareness_studio/tests/literature_bridge/**`,
`docs/awareness_studio/literature_bridge.md`. Touches nothing in
`tools/literature_evidence/**` (read-only canonical producer, only
ever imported from), `apps/awareness_studio/src/awareness_studio/research_cycle/**`
(read-only target schema, only ever imported from), claim-gate
implementation paths, network/download infrastructure, or any other
protected path.

## What this is

An **input-only evidence-ingestion bridge**, not scientific
confirmation. It maps validated `tools.literature_evidence` records
(`LiteratureRecord`, `ClaimRecord`) into `awareness_studio.research_cycle`'s
typed input schema (`SourceSnapshot`, `Claim`) so a research cycle can
use literature as hypothesis-generating input — never as `EvidenceRecord`,
never as anything research_cycle's own model would treat as confirmed,
empirical, causal, or formal-statistical evidence.

This bridge does not append anything to the research-cycle ledger
itself — it is a pure, side-effect-free mapping function. A caller
(outside this package's scope) is responsible for actually appending
the produced records to a specific cycle's ledger via
`ResearchCycleLedger`.

## The mapping contract

### `bridge_source(record: LiteratureRecord, *, cycle_id, snapshot=None) -> BridgeOutcome`

1. Calls `tools.literature_evidence.validation.validate_record(record, snapshot)` itself — **never re-validates more loosely** than the canonical producer. A non-`"valid"` result refuses to bridge, preserving the exact validation state (`rejected_missing_identity`, `rejected_fabricated_identifier`, `rejected_invalid_checksum`, `rejected_unsupported_publication_status`) in the outcome's `reason`.
2. Refuses (preserving the state) if the source's own lifecycle `status` is not `"active"` — `disputed`/`superseded`/`retracted` are visible, explicit refusal reasons, never silently bridged as if nothing were wrong.
3. Refuses (`missing_snapshot: ...`) if no `content_checksum` or `excerpt_hash` is available at all — **never invents a checksum**.
4. On success, produces a `research_cycle.models.SourceSnapshot` with:
   - `source_sha256` = the record's own (already-validated) checksum.
   - `data_mode = "literature_metadata"` — a fixed value that never triggers research_cycle's `synthetic_demo`/`empirical` promotion checks.
   - `evidence_class` mapped from the literature record's `evidence_class` (`hypothesis`/`theoretical`/`review_required` → `EvidenceClass.HYPOTHESIS`; `proxy` → `EvidenceClass.PROXY_INFERENCE`) — **never** `FORMAL_STATISTICAL_EVIDENCE` or `DESCRIPTIVE_EMPIRICAL`.
   - `source_format` = the literature record's `publication_type`, preserved verbatim.
   - `scientific_limitations` synthesized *only* from fields the source record already carries (publication_type, review_status, evidence_class) — never a new invented fact.
   - `metadata` carrying identifier, identifier_type, authors, venue, publication_date, and citation_relations verbatim.

### `bridge_claim(claim: ClaimRecord, *, cycle_id, source_snapshot_id) -> BridgeOutcome`

Maps to a `research_cycle.models.Claim` — never a `Hypothesis` directly (which requires non-empty `claim_ids` this bridge has no legitimate value for) and never an `EvidenceRecord`. `evidence_ids = (source_snapshot_id,)`: *"the evidence that this claim was made in the literature is the citation itself,"* never evidence that the claim is true. `evidence_class` is always `EvidenceClass.HYPOTHESIS` (literature ingestion never emits `PROXY_INFERENCE`, so research_cycle's causal/mechanistic-language guard for proxy claims never fires here — hypothesizing causation is ordinary pre-evidence science, consistent with research_cycle's own test suite).

1. Refuses if `claim.status != "active"` (preserves disputed claims explicitly).
2. Maps `claim_kind` → `Claim.status`: `"hypothesis"` → `"PENDING"`, `"review_required"` → `"REVIEW_REQUIRED"` — **a claim downgrade (e.g. via literature_evidence's own `mark_claim_review_required`) is preserved as a status change, never silently lost.**

## Preserved states (requirement 6)

| Literature-evidence state | Bridge behavior |
|---|---|
| `valid` + `active` + checksum present | Bridged |
| `rejected_missing_identity` | Not bridged; reason preserved verbatim |
| `rejected_fabricated_identifier` (unresolved identifier) | Not bridged; reason preserved verbatim |
| `rejected_invalid_checksum` (checksum mismatch) | Not bridged; reason preserved verbatim |
| `rejected_unsupported_publication_status` | Not bridged; reason preserved verbatim |
| `preprint` / `theory_paper` publication_type | Bridged, with an explicit added limitation (peer review / theoretical-framework caveat) |
| Source `status` = `disputed`/`superseded`/`retracted` | Not bridged; `source_status=<value>` preserved |
| Missing snapshot (no checksum at all) | Not bridged; `missing_snapshot: ...` preserved, never fabricated |
| Claim `status != "active"` (disputed claim) | Not bridged; `claim_status=<value>` preserved |
| Claim downgraded `hypothesis → review_required` | Bridged with `status = "REVIEW_REQUIRED"` instead of `"PENDING"` |

## Network policy (requirement 3)

This bridge never resolves an identifier over the network — it never
imports or calls `tools.literature_evidence.network`. Identifier
resolution (DOI/arXiv lookups) is exclusively that package's own,
separately opt-in concern; this bridge only ever consumes records the
caller has already constructed/validated locally.

## Never promotes literature into confirmed evidence (requirements 4, 5)

- `evidence_class` is never mapped to `FORMAL_STATISTICAL_EVIDENCE` or `DESCRIPTIVE_EMPIRICAL` for any literature-evidence input (`test_bridge_source_all_evidence_classes_map_to_non_confirmed_values` exhaustively checks all four literature evidence classes).
- `data_mode` is always the fixed `"literature_metadata"` value, never `"empirical"` or `"synthetic_demo"`.
- Claims are always `Claim` records with `evidence_class = HYPOTHESIS`, never wired into an `EvidenceRecord`/`RunRecordLink`/`ValidationReport` — this bridge does not implement, and does not attempt, the additional machinery that would be needed to make literature look like a completed experimental result.
- A valid, well-formed identifier is never treated as scientifically confirmed — `bridge_source`'s success only means "this citation is well-formed and internally consistent," a status research_cycle's own `SourceSnapshot.evidence_class` vocabulary makes explicit (`HYPOTHESIS`/`PROXY_INFERENCE`, not `FORMAL_STATISTICAL_EVIDENCE`).

## Test commands

```bash
cd apps/awareness_studio && python -m pytest tests/literature_bridge -q         # 24 passed
cd apps/awareness_studio && python -m pytest tests/research_cycle tests/research_graph -q  # Awareness Studio compatibility (55 passed, 1 pre-existing unrelated failure)
python -m pytest tests/literature_evidence -q                                   # 36 passed (canonical producer, unaffected)
python -m pytest tests/research_claim_gate -q                                   # 16 passed (claim-gate, unaffected)
python -m governance.validate                                                    # 4/4 specs pass
python -m compileall -q apps/awareness_studio/src/awareness_studio/literature_bridge apps/awareness_studio/tests/literature_bridge
git diff --cached --check                                                        # no whitespace errors
```

No test opens a socket: `test_no_network_during_full_bridge_cycle` patches
`socket.socket` to raise during a full source+claim bridge cycle;
`test_module_import_touches_no_network` confirms merely importing the
bridge touches nothing. `test_no_heavy_import` runs in an isolated
subprocess and confirms none of numpy/scipy/sklearn/mne/torch/pandas/requests
load.

**Pre-existing, unrelated test issues observed while running the full
Awareness Studio suite** (not introduced by this change, not touched by
this branch): `tests/test_cmd_orchestrate.py`, `tests/test_export_sim_artifacts.py`,
`tests/test_web_app.py`, `tests/test_web_tool_routes.py`, `tests/test_web_ui.py`
fail to collect because `fastapi`/a local `apps/awareness_studio/tools`
path is unavailable in this environment; `tests/research_graph/test_invariants_and_isolation.py::test_no_heavy_imports`
fails because its own subprocess probe doesn't set `PYTHONPATH=src`.
None of these touch `literature_bridge`.

## Required test scenarios (all covered)

valid peer-reviewed metadata · preprint · theory paper · unresolved
identifier · missing source content · checksum mismatch · claim
downgrade · no-network · finite JSON — see
`apps/awareness_studio/tests/literature_bridge/test_mapping.py`.

## Known limitations

- `bridge_claim` requires a caller-supplied `source_snapshot_id` — it
  does not itself look up or verify that a matching `SourceSnapshot`
  was actually bridged first; a caller wiring this into a real research
  cycle should bridge the source before the claim and pass through the
  resulting `snapshot_id`.
- Citation relations are passed through verbatim as metadata on the
  bridged `SourceSnapshot`; this bridge does not itself resolve or
  validate cross-source citation graphs.
- This bridge does not write to `ResearchCycleLedger` — appending a
  bridged record to an actual research cycle, and any subsequent
  claim-gate evaluation of it, is deliberately out of scope here.

