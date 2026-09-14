# Research claim language

This note is the language contract for `shared/research_claims` and
`scripts/validate_research_claims.py`. It does not compute evidence. It
does not rewrite reports.

Related context: PR #219 / #226 (proxy versus formal evidence), PR #229
(dataset provenance), PR #234 (artifact-consumer migration). PR #236 is
integrated-only and is not merged. Historical repository prose about
quantum coherence, consciousness, exceptional points, meditation,
sedation, and topology remains historical until a claim record says
otherwise.

## Purpose

Reports and documentation must not promote unsupported scientific
language. Every reusable claim is stored as a record and audited
locally. The auditor is deterministic, stdlib-only at the CLI boundary,
and never edits `text` or numeric results.

## Claim record

Required fields:

| Field | Meaning |
| --- | --- |
| `claim_id` | Stable identifier |
| `text` | Exact claim language (immutable to the auditor) |
| `claim_category` | Closed classification |
| `evidence_class` | Closed classification (may match or further locate the claim) |
| `provenance_reference` | Dataset, file, URI, or source pointer |
| `data_origin` | Origin label (`openneuro:ds005620`, `synthetic_fixture`, …) |
| `empirical_synthetic_status` | `empirical` / `synthetic` / `mixed` / `unknown` / `not_applicable` |
| `proxy_formal_status` | `proxy` / `formal` / `not_applicable` / `unknown` |
| `test_reference` | Test or contract that can fail the claim |
| `required_controls` | Declared controls |
| `falsifiability_condition` | How the claim would fail |
| `allowed_language` | Phrases this record may use |
| `prohibited_language` | Phrases this record must not use |
| `reviewer_state` | Review marker |
| `last_reviewed` | Date or review token |

## Classifications

- `engineering_fact`
- `benchmark_result`
- `synthetic_demonstration`
- `empirical_observation`
- `proxy_inference`
- `formal_statistical_evidence`
- `hypothesis`
- `speculation`
- `unsupported_claim`
- `historical_context`

`PASS` from this auditor means the record is internally consistent. It
is not a scientific `PASS` under the falsification contract
(`docs/scientific_falsification/README.md`). Scientific `PASS` remains
reserved for a finite formal Bayes factor `K > 100` with valid empirical
data, complete provenance, passing controls, and known multiplicity.

## Rules

1. Synthetic output cannot support biological confirmation.
2. Proxy K cannot be called a formal Bayes factor.
3. A numerical beta-1 proxy cannot be called proof of consciousness.
4. Graph beta-1 cannot be called spatial topological charge. Graph
   cycle rank, spatial winding / topological charge, and scalar
   chirality stay distinct (`graph_beta1`, `spatial_winding_q`,
   `scalar_chirality`).
5. A fitted exceptional point cannot be called a biological phase
   transition without empirical validation.
6. A decoherence simulation cannot be called evidence of biological
   quantum coherence without independently validated inputs.
7. Missing provenance must downgrade claims.
8. Claims must contain a falsification condition or be labeled
   `speculation` (or `historical_context` / `unsupported_claim`).
9. Reports must preserve uncertainty and limitations.
10. The validator must never rewrite scientific results. Findings are
    audit metadata only.

## Unsafe examples

Allowed when scoped correctly:

- "engineering validation only"
- "synthetic demonstration"
- "proxy K" / "information-criterion ratio"
- "formal K from a declared marginal likelihood"
- "does not confirm a biological mechanism"
- "historical language; not a current empirical claim"

Prohibited as promoted conclusions:

- "proves consciousness" / "proof of consciousness"
- "biological confirmation" from synthetic or proxy output
- "proxy K is a formal Bayes factor"
- "graph beta-1 is spatial topological charge"
- "fitted EP is a biological phase transition" without empirical validation
- "decoherence simulation is evidence of biological quantum coherence"
- "without limitation" / "no uncertainty" / "definitively proves"

Historical files may retain old wording only when classified
`historical_context` or `unsupported_claim` and not used as current
evidence.

## CLI

```text
python scripts/validate_research_claims.py \
  --input claims.json \
  --output claim_audit.json
```

Exit `0` only when every record is `PASS`. `FAIL` and `DOWNGRADED`
records are written into `claim_audit.json` without altering the input
file.

## Limitations

- Language audit is not model comparison.
- Completing metadata does not create a formal likelihood.
- Proxy evidence cannot cross the `K > 100` scientific gate.
- Missing or fixture provenance cannot support empirical promotion.
- PITNN / open-quantum / exceptional-point layers remain speculative
  until independently identifiable on empirical data.
