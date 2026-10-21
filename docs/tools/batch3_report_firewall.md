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
negations, limitation sections, fenced and indented code, Markdown blockquotes
including unmarked lazy paragraph-continuation lines, inline backtick code,
double/curly/single-quoted spans, and fixture/example JSON fields are excluded
or handled conservatively. Simple punctuation, comma-led
boundaries before common clause subjects, and coordinating conjunctions are
used so a nearby negation or caution does not suppress a separate assertive
clause; this is not a grammar parser and remains a heuristic.

Quoted spans are masked before pattern matching, so a quoted occurrence does
not hide a later unquoted occurrence, and a pattern does not bridge across a
quoted span.

This is an advisory layer, not an evidence evaluator. A finding is not proof of
misconduct or proof that a claim is false; no finding is not proof that a claim
is true. Evidence-reference presence is only a textual/field-presence signal,
not source verification. The checker never rewrites reports, assigns a
scientific status, emits a scientific pass, or emits scientific `VALIDATED`.
Structured `scientific_status: VALIDATED` is still warned on when unrelated
metadata says `validation_scope: software`.
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

## Heuristic boundaries

For prose, the lightweight clause splitter recognizes `.`, `!`, `?`, `;`, or
`:` followed by whitespace; an en or em dash surrounded by whitespace; and the
coordinating words `and`, `but`, `or`, `nor`, `yet`, `whereas`, `while`,
`although`, and `though` when surrounded by whitespace. A comma is a boundary
only when followed by whitespace and one of these subjects: `the`, `this`,
`these`, `those`, `it`, `they`, `we`, `result(s)`, `finding(s)`, `analysis`,
`intervention`, `model`, `data`, `output`, `evidence`, `claim`, or `report`.
Recognized negation/caution in one such fragment should not suppress a separate
fragment, but this is not grammar parsing. Unlisted comma-led subjects, complex
syntax, and a qualifier and assertion in one fragment may still be missed or
over-suppressed.

Fenced code is skipped until a closing fence uses the same marker, has at least
the opening run length, and has no non-whitespace suffix. Four-space/tab-
indented code and blockquote paragraphs (including nonblank unmarked lazy
continuations until a blank line or recognized block starter) are skipped.
Inline code is excluded only when matching, unescaped backtick runs have equal
length; backslash-escaped backticks are literal delimiters. Paired straight
double/single and curly quotes are excluded; apostrophes between word characters are treated as
apostrophes, while unmatched quote delimiters do not hide the paragraph tail.
Lazy blockquote continuation handling recognizes only a small set of block
starters; it is not a complete CommonMark parser. Nested/malformed Markdown
and attribution remain heuristic edge cases.

The `certainty` label is a heuristic category, not a probability or an
evidentiary weight. A warning is not proof that a claim is false or misconduct
occurred; an empty finding list does not prove that claims are true. Evidence
references are not opened or verified.

## CLI and deterministic limits

Exit code `0` means the explicit selection was scanned. It may still include
warnings, such as `REPORT_NOT_PARSEABLE` for malformed JSON or invalid UTF-8;
content checks are not performed for that file. Path-selection failures,
including traversal, directory selection, unsupported extensions, missing
files, or size/count limits, return exit code `2`, a JSON `input_errors` list,
and no report findings. Directories are never recursively expanded. Repeating
the same invalid selection on a stable root produces the same error payload.
Path resolution and containment checks are not a race-resistant filesystem
sandbox against concurrent replacement of path components or file contents;
scan a stable local tree.

- Detection is regex/structure based, not semantic inference. Negation and
  caution handling is local to simple punctuation, selected comma-led clause
  subjects, and coordinating conjunctions; complex grammar, attribution, and
  mixed claims may still require human review.
- Single-quote pairing is heuristic; apostrophes, unmatched quotes, and nested
  quoted spans can be ambiguous. Review any finding in that context.
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
