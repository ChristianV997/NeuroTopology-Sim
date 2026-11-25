# Awareness Studio Evidence Registry

Branch: `claude/awareness-studio-evidence-registry`, based on latest
`origin/main` (`62aa8fee786abf916ab0aa2b7e7b91c570fee119`). Owns
exclusively: `tools/awareness_studio_research/**`,
`scripts/awareness_studio_research.py`, `tests/awareness_studio_research/**`,
`docs/awareness_studio/research_evidence_registry.md`. Touches nothing
in `apps/awareness_studio/**` (UI routes, FastAPI routes, the research-cycle
inventory in `web/research_ops.py`, or any paper compiler/Bayesian
falsification/feature-extractor code -- all either owned by sibling
branches in this same parallel round or pre-existing and out of scope),
`tools/literature_senses/**` (a separate, already-merged system with
similar aims -- read for context only, never imported from or modified),
scientific solvers, or dashboard routes.

## What this is

An offline-first, provenance-rich, append-only evidence registry for
literature sources, extracted claims, physiological/neural correlates,
and their links to hypotheses/datasets/experiments. It is a **research
record, not an autonomous authority**: it never asserts a claim is true,
never silently rewrites a prior record, and never fetches anything over
the network unless a caller explicitly opts in.

## Storage model: append-only JSONL event log, in-memory projection

`store.EvidenceRegistry` is bound to one JSONL file. Every mutation
(`add_source`, `add_claim`, `supersede_source`, `dispute_source`,
`downgrade_source`, `dispute_claim`, ...) appends exactly one event and
never edits or truncates a prior line. The "current state" returned by
`list_sources()`/`get_claim()`/etc. is a deterministic projection
rebuilt by replaying the log from position zero on every call -- so the
full history is always recoverable (`audit_history()`), and re-adding an
existing id raises `ImmutabilityError` rather than silently overwriting
it. JSONL (not SQLite) was chosen as the single backing format: append
is O(1) and the replay-to-projection model gives the immutability
guarantee directly, with no second schema to keep in sync.

**A real implementation bug this caught during development:** the first
version of `_project()` picked an entity's dict key by attribute-sniffing
(`hasattr(record, "source_id")`, then `"claim_id"`, ...). `ExtractedClaim`
carries *both* a `claim_id` and a `source_id` field, so every claim's
key resolved to its parent source's id instead of its own -- claims
silently vanished behind whichever source they cited, and
`get_claim()` returned `None` for every claim after replay. Fixed by
keying strictly off the caller-supplied `entity_type` (a fixed
`_ID_FIELD_BY_ENTITY_TYPE` map), never by inspecting the record's own
attributes. Caught by `test_claim_extraction_fixture_and_dispute`,
`test_unsupported_claim_recorded_as_such`, and
`test_theoretical_paper_claim_status`, all of which failed with
`AttributeError: 'NoneType' object has no attribute ...` before the fix.

**A second real bug:** dataclass fields typed `tuple[str, ...]`
(`authors`, `tags`, `limitations`, ...) survive a fresh constructor call
as tuples, but round-tripping through the JSONL log (`json.dumps` then
`json.loads`) turns them into plain lists, since JSON has no tuple type.
A record replayed from the log therefore silently differed in type from
one just constructed, breaking hashability/equality expectations
downstream. Fixed with a `__post_init__` coercion (`_coerce_tuple_fields`)
on every dataclass with tuple fields, so a record is always the same
shape regardless of whether it came from a constructor or a replay.

## Schema (requirement 2)

`models.py` defines: `LiteratureSource`, `ExtractedClaim`, `Correlate`
(neural/physiological correlate), `HypothesisLink`, `DatasetLink`,
`ExperimentLink`, `EvidenceUpdate` (the audit-event record itself).
Citation and retrieval metadata are embedded directly in
`LiteratureSource` (title/authors/doi/url/publication_date/
retrieval_timestamp/source_checksum) plus a `retrieval_metadata` dict
recording `{method, network_used}` -- there is no separate table for
this, since every source record already carries its own provenance.

Every `LiteratureSource` includes (requirement 3): `title`, `authors`,
`doi`/`arxiv_id`/`url`, `publication_date`, `source_type`,
`retrieval_timestamp`, `source_checksum`, `abstract_or_excerpt` (bounded
to 2000 chars), `peer_review_status`, `evidence_tier`, `limitations`,
`license_or_access_status`.

Every `ExtractedClaim` includes (requirement 4): `claim_text` (exact),
`claim_class`, `source_location`, `supporting_excerpt`, `confidence`,
`alternative_interpretation`, `bio_vs_methodological`,
`linked_hypothesis`, and `claim_status` (one of `empirical`,
`theoretical`, `proxy`, `speculative`, `unsupported`).

## Importers (requirement 5) -- offline by default

`importers.py`: `import_json_export`, `import_csv_export` (explicit
local file exports), `import_arxiv_metadata`, `import_doi_metadata`
(both take an **operator-supplied** metadata dict -- never fetch
anything themselves), `import_manual_capture` (manually captured
HTML/text + citation metadata). `network.py` gates the only two actual
network-capable functions (`fetch_arxiv_metadata`, `fetch_doi_metadata`)
behind an explicit `allow_network=True` keyword; calling either without
it raises `NetworkDisabledError`. Neither is used by any importer or by
any code path exercised in the default test suite -- ingestion is
offline-first end to end, and this package never scrapes an arbitrary
site (only arXiv's export API and a DOI/Crossref resolver, both narrow
and well-known, and only on explicit opt-in).

## Deduplication (requirement 7)

`dedupe.find_duplicates` checks, in order: DOI match, arXiv-ID match,
normalized-title match, and checksum match (all via `checksum.py`'s
`normalize_text`/`content_checksum`) -- independently implemented for
this package, not imported from `tools/integration_reconciliation`'s
similarly-named logic (a different domain -- code-ownership overlap, not
literature dedup) or from `tools/literature_senses` (a different,
already-merged system).

## Query capabilities (requirement 8)

`query.QUERY_PACKS` defines fixed, deterministic keyword sets for:
`triadic_connectivity`, `higher_order_spectra`, `respiration_autonomic`,
`discernment`, `nonattachment`, `decentering`, `hypergraph_forecasting`,
`null_model_methodology`. `run_query_pack()` does case-insensitive
substring matching against `claim_text` + `tags` + `supporting_excerpt`
and returns results sorted by `claim_id` -- never an LLM call, never
fuzzy, always byte-identical across repeats.

## Verification workflow: never assume the prompt's claims are correct

`verification.verify_source_claim` compares an operator/prompt-claimed
identity against an independently obtained `confirmed` fact dict (or
`None` if no independent check was attempted) and returns one of
`verified` / `unverified` / `disputed`, plus an explicit list of
disagreement strings. `confirmed=None` is always `unverified`
(`T3_unverified_claimed`), never silently treated as confirmed.

### Real verification of the five scientific sources named in the task prompt (2026-09-07)

Verified via `WebSearch` (network access to `arxiv.org` itself was
blocked by this environment's egress proxy, so identity was confirmed
through search-engine-indexed metadata rather than a direct fetch):

| Claimed | Result |
|---|---|
| arXiv:2609.03987, "triadic functional connectivity" | **Confirmed.** Real paper: "High-Order Triadic Functional Connectivity in the Brain and Beyond" (Li, Seraji, Wang, Pearlson, Calhoun), submitted 2026-09-03. Topic matches. |
| arXiv:2609.03172, "higher-order spectra" | **Confirmed.** Real paper: "Modulation Analysis with Higher-Order Spectra" (Kovach, Kumar). Topic matches. |
| DOI:10.1016/j.neuron.2026.04.044, "slow breathing and inter-organ dynamics" | **Confirmed.** Real paper: "Slow breathing impacts inter-organ dynamics modulating brain function and risk behavior" (Huang et al., *Neuron*, May 2026). Topic matches closely. |
| DOI:10.1007/s12671-026-02976-7, "discernment and nonjudgment" | **Disagreement.** This exact DOI could not be independently located. A closely topic-matched *Mindfulness* article exists -- "Being Mindful with Discernment: Development and Validation of the Mindfulness-Discernment Scale (MDS)" -- but at a **different** DOI, `10.1007/s12671-026-02770-5`. Recorded as `disputed`/`T4_disputed`, not silently substituted. |
| DOI:10.3389/fpsyg.2026.1938434, "Buddhist meditation training ecology" | **Disagreement.** This exact DOI could not be independently located in *Frontiers in Psychology*'s 2026 volume. Adjacent 2026 Buddhist-meditation articles exist at other DOIs (e.g. `10.3389/fpsyg.2026.1711922`, `10.3389/fpsyg.2026.1815107`) but none match this identifier or an "ecology" framing. Recorded as `disputed`/`T4_disputed`. |

Full claimed/confirmed metadata and the exact disagreement text are in
`tests/awareness_studio_research/fixtures/five_scientific_sources.json`,
exercised end to end by `test_verification.py::test_five_real_sources_fixture_two_disagreements`
and `test_store_audit.py::test_real_five_sources_ingested_with_correct_dispositions`
(3 verified, 2 disputed -- never all 5 silently accepted as verified).

## Test commands

```bash
PYTHONPATH=. python -m pytest tests/awareness_studio_research -q   # 50 passed
python -m compileall -q tools/awareness_studio_research scripts/awareness_studio_research.py tests/awareness_studio_research
python -m governance.validate                                      # 4/4 specs pass (baseline, unaffected)
python -m pytest apps/awareness_studio/tests/test_research_ops.py -q  # 3 passed (closest existing "research-cycle" test; pre-existing, unaffected)
```

No test opens a socket: `test_offline_operation.py::test_no_socket_calls_during_full_ingest_cycle`
patches `socket.socket` to raise and runs a full ingest cycle through
it; `test_no_hidden_network_import_at_module_load` confirms merely
importing `network.py` never touches the network either (only calling
its functions with `allow_network=True` would). A separate isolated
subprocess test (`test_isolated_subprocess_cli_ingest_and_query`) drives
`scripts/awareness_studio_research.py` end to end as a real child
process. `test_no_heavy_import_in_package_modules` runs every package
module in an isolated subprocess and asserts none of
numpy/scipy/sklearn/mne/torch/pandas end up in `sys.modules`.

## Required test scenarios (all covered)

source ingestion · duplicate source · claim extraction fixture ·
provenance checksum · unsupported claim · theoretical paper · preprint ·
missing metadata · offline operation · deterministic queries ·
no-heavy-import behavior -- see `tests/awareness_studio_research/`.

## Known limitations

- Verification (`verify_source_claim`) checks identity (DOI/arXiv
  existence, and title equality when an exact title claim is actually
  made) -- it does not itself do topic-relevance scoring; that is a
  separate, simpler substring check used only in the five-real-sources
  test, not part of the core module.
- `network.py`'s `fetch_arxiv_metadata`/`fetch_doi_metadata` are
  provided for an operator to opt into explicitly (e.g. from a REPL or
  a future CLI flag); the shipped CLI (`scripts/awareness_studio_research.py`)
  does not itself expose a flag that calls them, keeping every default
  invocation offline.
- Correlates, hypothesis/dataset/experiment links are append-only,
  single-version records in this iteration (no supersede/dispute
  workflow yet) -- only `LiteratureSource` and `ExtractedClaim` have the
  full downgrade/supersede/dispute lifecycle, since those are the two
  record types the task's audit-history requirement (10) centers on.
- `hypothesis_id` on `HypothesisLink` is a free-text reference (e.g. a
  `governance/specs/HYP-*.yaml` `spec_id`) -- this package does not
  import or validate against `governance/specs/` to stay fully decoupled
  from sibling-owned validation logic.
