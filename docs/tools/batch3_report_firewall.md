# Batch 3 report-language firewall (advisory)

`scripts/check_batch3_report_language.py` checks only the Markdown/JSON report
files explicitly named by the caller. It reads files under a required bounded
root, rejects traversal and symlink paths, limits selected file sizes/counts,
and performs no network, model, subprocess, or report-generation work.

```powershell
python scripts/check_batch3_report_language.py --root .\local-reports summary.md results.json
```

The JSON output contains `findings` with a relative file, Markdown line or JSON
pointer, rule, warning severity, certainty, and a human-review recommendation.
Findings can cover synthetic/fixture-to-empirical wording, software conformance
presented as biological validation, asserted causal/mechanistic language,
replication without an independent reference, structured evidence/status
conflicts, missing references, and ambiguous validation labels. Explicit
negations, limitation sections, fenced examples, Markdown blockquotes, quoted
phrases, and fixture/example JSON fields are excluded or handled conservatively.

This is an advisory layer, not an evidence evaluator. A finding is not proof of
misconduct or proof that a claim is false; no finding is not proof that a claim
is true. Evidence-reference presence is only a textual/field-presence signal,
not source verification. The checker never rewrites reports, assigns a
scientific status, emits a scientific pass, or emits scientific `VALIDATED`.
It does not replace the research-claim auditor, claim/evidence promotion gate,
hypothesis-to-measurement checks, provenance system, or report generators.

Existing checks overlap in narrower ways: `tools/check_claim_guardrails.py`
scans repository text for a short banned-phrase list;
`tools/validate_ontology_claim_language.py` applies ontology-specific phrase
rules and a baseline; `shared/research_claims/audit.py` audits structured claim
records; `tools/research_cycle_release/language.py` checks report metadata; and
the Awareness Studio research-cycle renderer applies its own claim gate while
generating drafts. None provides the bounded, explicit-file, advisory
cross-format language/status review implemented here. The checker reuses the
shared claim-language ceiling catalog but does not call a promotion gate.

## Deterministic limits

- Detection is regex/structure based, not semantic inference. Negation and
  caution handling is deliberately local; complicated prose, mixed clauses,
  attribution, and citations may still require human review.
- A citation, DOI, URL, or evidence-reference field is not opened or verified.
- JSON is parsed strictly; malformed/non-finite JSON gets a file-level review
  finding and is not scanned as free text.
- Only `.md` and `.json` files are supported. No recursive directory scan is
  available. Limits are 100 explicit files, 2 MB per file, and 10 MB total.
- The checker produces warnings only. Findings never block execution or change
  evidence classes, claims, or report contents.

Run the local fixture tests with either the repository's usual pytest runner or
the Python standard-library runner (the tests are compatible with both):

```powershell
python -m pytest tests/tools/batch3_report_firewall -q
python -m unittest discover -s tests/tools/batch3_report_firewall -p 'test_*.py' -v
```
