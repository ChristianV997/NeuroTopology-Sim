# Awareness Studio Source Resolution

Branch: `claude/awareness-source-resolution`, based on latest `origin/main`.
Owns exclusively: `tools/awareness_studio_research/source_resolution.py`,
`scripts/resolve_awareness_sources.py`,
`tests/awareness_studio_research/test_source_resolution.py`,
`docs/awareness_studio/source_resolution.md`,
`fixtures/awareness_source_resolution/**`. Touches nothing in
`tools/awareness_studio_research/store.py` or `network.py` (owned by
PR #276, the evidence registry itself, not yet merged into `main` as of
this branch's base commit -- treated as read-only and not imported from,
per the same zero-cross-dependency convention this session has used for
every parallel package), the research-cycle orchestrator, the
hypothesis registry, scientific analysis code, or dashboard routes.

## What this is

A decision layer that answers, for one claimed literature source: "which
real, independently-observed record (if any) does this actually refer
to, and how confident is that?" It never edits the evidence registry's
own store, and it is fully self-contained -- no import of `store.py`,
`models.py`, or anything else from the registry package, since that
package is owned by a sibling branch in this same parallel round and
this branch must have zero dependency on it (whether or not it has
merged yet).

**Source identity verification is not scientific claim verification.**
Confirming *which paper* a DOI refers to says nothing about whether that
paper's findings are correct. `claim_availability()` exists specifically
to keep the two separate: claim extraction is only marked `"available"`
once identity resolution has actually confirmed a specific source
(`confirmed_identity`, or a `duplicate`/`superseded` state that itself
resolves to a confirmed target) -- every other state, including
`ambiguous_identity` and `disputed_identity`, reports `"unavailable"`.

## The six resolution states

| State | Meaning |
|---|---|
| `confirmed_identity` | A candidate (or operator correction) matched with a strong signal (DOI, arXiv id, or checksum) at or above the confidence threshold. |
| `disputed_identity` | Some evidence was checked, but it contradicts or fails to confirm the claim (e.g. the best candidate only shares weak signals, or the claim was confirmed nonexistent). |
| `ambiguous_identity` | Two or more candidates tie at the same non-zero match score -- resolution cannot pick a single identity. |
| `unavailable` | No independent candidate data was supplied at all to check the claim against. |
| `superseded` | The caller has explicitly marked this resolution as superseded by a newer one (`superseded_by`). |
| `duplicate` | The caller has explicitly determined this claimed source is identical to an already-resolved one (`duplicate_of`). |

## Identity verification signals (requirement 2)

`score_candidate()` checks, with a weighted contribution towards a
0-1 match score: DOI match (strong, 0.45), arXiv-id match (strong,
0.45), checksum match (strong, 0.4), normalized-title match (0.25),
author overlap via surname-normalized Jaccard similarity (up to 0.15,
scaled by overlap), publication-year proximity (0.1), and journal match
(0.15). `confirmed_identity` requires both the combined score to clear
`_CONFIRMED_THRESHOLD` (0.55) **and** at least one strong signal to have
fired -- a paper that merely shares a journal and publication year with
the claim is never confirmed on that basis alone.

## Operator-provided correction (requirement 2, 3)

An operator correction is treated as an authoritative human override of
a claim already known to be wrong elsewhere -- it is deliberately **not**
re-scored against the (disputed) original claim's own fields, since the
whole point of a correction is that those fields were wrong. It is
trusted only if it itself carries a verifiable DOI or arXiv id and was
not itself independently confirmed nonexistent; otherwise it is reported
`disputed_identity`, never silently accepted just because an operator
supplied *something*.

## Never silently replace a disputed record (requirement 3)

`SourceResolutionLog` is an append-only JSONL log, independently
implemented (no import of the registry's `EvidenceRegistry`). Every
call to `record_resolution()` appends exactly one
`ResolutionEvent` -- `original_source`, `candidate_source`, `evidence`,
`resolver`, `date`, `confidence`, `reason` -- and never edits or removes
a prior line. `history_for()` replays every event ever recorded for a
given source ref; `current_resolution()` returns only the most recent
one. Resolving a source a second time (e.g. after a corrected DOI
arrives) always appends a new event: the original disputed attempt
remains permanently visible in `history_for()`, it is never overwritten.

## The five source families (requirement 4)

`fixtures/awareness_source_resolution/five_source_families.json` carries
real identity data (gathered via `WebSearch` on 2026-09-07/08, since
`arxiv.org` itself is blocked by this environment's egress proxy) for:
triadic functional connectivity, higher-order spectra, slow breathing,
discernment/nonjudgment, and Buddhist training ecology.

| Family | Result |
|---|---|
| triadic functional connectivity | `confirmed_identity` — arXiv:2609.03987 matches a real, findable paper. |
| higher-order spectra | `confirmed_identity` — arXiv:2609.03172 matches a real, findable paper. |
| slow breathing | `confirmed_identity` — DOI:10.1016/j.neuron.2026.04.044 matches a real, findable *Neuron* paper. |
| discernment/nonjudgment | `disputed_identity` without an operator correction (the exact claimed DOI 10.1007/s12671-026-02976-7 does not resolve to any independently locatable record); `confirmed_identity` once an operator supplies the actual DOI (10.1007/s12671-026-02770-5) as a correction. Both the original disputed attempt and the corrected confirmation are retained in the log — the disputed event is never deleted. |
| Buddhist training ecology | `disputed_identity` — the claimed DOI (10.3389/fpsyg.2026.1938434) does not match either of the two adjacent 2026 Frontiers in Psychology articles found; neither shares a strong identity signal with the claim, so it remains genuinely disputed with no operator correction supplied. Its claims stay `unavailable`. |

## Test commands

```bash
PYTHONPATH=. python -m pytest tests/awareness_studio_research/test_source_resolution.py -q
PYTHONPATH=. python -m pytest tests/awareness_studio_research -q   # full evidence-registry + resolution suite (registry pieces run once PR #276 is present)
python -m compileall -q tools/awareness_studio_research/source_resolution.py scripts/resolve_awareness_sources.py tests/awareness_studio_research/test_source_resolution.py
python -m governance.validate
```

No test opens a socket: every candidate/claimed identity in
`test_source_resolution.py` is a literal in-memory `SourceIdentity` or a
small local JSON fixture file; `test_no_network_fixture_mode` patches
`socket.socket` to raise and confirms a full resolve-and-log cycle still
succeeds.

## Known limitations

- This module has no dependency on, and does not itself write into, the
  evidence registry's own store (`store.py`) — a caller that wants a
  confirmed resolution reflected in the registry (e.g. via
  `supersede_source`/`dispute_source`) must do that wiring itself, once
  both branches are merged. That wiring was explicitly out of scope here
  (`store.py` is not to be modified, and importing it would create a
  cross-branch dependency this session's convention forbids).
- `author_overlap` is a surname-only, case/punctuation-insensitive
  Jaccard similarity — it will not catch two authors who share a surname
  but are different people, nor distinguish "J. Smith" from "K. Smith"
  beyond the surname; it is deliberately a weak (0.15-weighted) signal
  for exactly this reason, never sufficient on its own to confirm
  identity.
- `duplicate_of`/`superseded_by` are caller-supplied labels — this
  module does not itself search for which other resolution a source
  might duplicate or be superseded by (that discovery logic belongs to
  whichever caller wires this into a larger workflow).
