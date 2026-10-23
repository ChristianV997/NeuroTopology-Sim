# OSS Adoption Gates and Evidence Boundaries — 2026-10-16

> Candidate-specific compatibility evidence is maintained in the canonical
> inventory `docs/oss_compat/compatibility_inventory_20261017.json` and its
> audit (`docs/oss_compat/batch1_compatibility_audit_20261017.md`, PR #406).
> The stable candidate row IDs are `openmed`, `papergym`, `openresearch`,
> `rea`, and `autoresearch`; the existing-tool row `gudhi` carries the
> package/component-license caveat. This document intentionally does not
> duplicate their versions, licenses, or per-candidate assessments. The PRs
> remain independent artifacts; this is a documentation reference only, not
> runtime coupling.

Status: engineering and adoption routing only; project posture remains **HOLD /
SYNTHETIC_ONLY**. Nothing here is scientific evidence, a legal opinion,
security certification, or validation of a candidate's claims. The candidate
review below is historical (source access date 2026-10-16); use the canonical
inventory's dated evidence and limitations for candidate-specific facts. No
candidate was cloned, installed, executed, or copied for this review.

## Scope and provenance

- The adoption-gate change is limited to `oss_opportunities` validation,
  deterministic scoring, duplicate handling, and planner routing.
- The baseline recorded during the original review was
  `3f3fe8593303184cb88eef056c1322f3d4e57a16`; it is historical, not a current
  main reference.
- PR #375's source registry, `external_tools/`, and
  `tools/public_repo_harvest/` are not replaced or modified by these gates.
- Candidate scoring is an engineering-priority heuristic. It does not
  establish implementation suitability, security, compatibility, scientific
  validity, legal approval, or authorization to adopt.

## Adoption action vocabulary

The pipeline uses `oss_opportunities.validation.ALLOWED_RECOMMENDED_ACTION`:

- `integrate_as_optional_adapter` / `integrate_as_external_tool_record` — a
  possible engineering integration path, not authorization or completed work;
- `emulate_architecture_pattern` — pattern-level design comparison, no code
  copy;
- `create_docs_reference` — reference-only;
- `license_review_required` / `security_review_required` / `defer` — blocked
  pending the named review;
- `reject` — no defensible role identified by this heuristic.

Every output retains `REQUIRED_BLOCKED_ACTIONS`, including code-copy without
license review, automatic dependency installation, execution of untrusted
code, credential-required execution, automatic outreach, and automatic
marketing claims. A score cannot remove these blocks.

## Existing neuro tools — current-in-repository evidence from the historical review

These entries were observed in the repository during the 2026-10-16 review;
they are not a fresh dependency or security audit. Candidate-specific license
evidence is not duplicated here.

| Tool | Observed in repository | Scope note |
|---|---|---|
| MNE-Python | `external_tools/registry_seed.json`; `requirements-eeg.txt`; `data/preprocessing.py`; `dual_engine/data_adapters.py` | Existing use; this table makes no compatibility or security claim. |
| MNE-BIDS | Registry seed; `adapters/mne_bids.py`; feature-recipe modules; `requirements-eeg.txt` | A fuller layout reader was recorded as future work in `docs/mne_bids_adapter.md`. |
| MOABB | Registry seed; `dataset_importers/moabb_importer.py` | Metadata-only importer; no dataset acquisition is authorized by this note. |
| GUDHI | Registry seed; `requirements-research.txt`; `core/topology.py` | Candidate-specific package and component licensing is recorded only in canonical inventory row `gudhi`; repository-level MIT must not be read as blanket component clearance. |
| Ripser | `requirements-base.txt`; registry seed; `core/topological_filtration.py` | Existing use; optional `cripser` path is separately scoped. |

## Fail-closed adoption gates

- **Source identity:** repository names and URLs must be well-formed and
  consistent; malformed input is reported instead of throwing or being
  normalized into a different identity.
- **Review identity and state:** a license review must match the candidate's
  repository and observed license. Rejected or unknown review statuses cannot
  authorize a recommendation. A direct score call applies the same checks as
  batch planning.
- **Conflicting observations:** duplicate case-insensitive repository
  identities are not resolved by choosing the highest score. If observations
  disagree on the license string, the combined candidate is routed through
  `license_review_required` with the conflicting values retained as unresolved
  evidence — including when keyword matching would otherwise assign
  `reject_or_defer`. Case-only spelling differences do not create a false
  conflict.
- **Unknown license:** empty, `unknown`, `no-license`, `noassertion`, or
  unmatched strings stay in a high-risk tier and route to review; they are not
  treated as permissive and are not silently rejected solely because the
  leverage category is `reject_or_defer`.
- **Credentials:** a candidate marked as requiring credentials routes to
  `security_review_required`; credential-required execution remains blocked.
- **Duplicate records:** observations for the same repository are grouped
  deterministically and duplicate records are identified rather than scored
  as independent projects.
- **Evidence limits:** source labels, trend signals, stars, keyword matching,
  and engineering suitability do not establish compatibility, security,
  legal permission, construct validity, or scientific truth.

## License-risk model

`oss_opportunities.license_review.classify_license_risk` is an offline string
classification against a fixed policy ladder. It does not fetch, parse, or
verify an upstream license and is not a legal opinion. `review_status` defaults
to `heuristic_unreviewed`; only a human-set `human_reviewed` means a person
performed the review. Even that flag is metadata, not legal clearance.

Only the `permissive_low` tier may carry the copy-permitting default policy.
Unknown, conflicting, or malformed evidence remains blocked. Repository
license labels, package declarations, and transitive/component licenses are
distinct evidence scopes; candidate-specific findings belong in the canonical
inventory rather than being copied into this runtime-routing document.

## Offline tests and limitations

Focused synthetic/offline tests are in `tests/test_oss_adoption_gates.py`.
They exercise input validation, review matching/status, conflicting duplicate
licenses, case-insensitive identity behavior, and planner routing. They test
the repository's engineering gates only; they do not validate upstream
licenses, security, compatibility, scientific results, or biological claims.

The heuristic can still miss semantics not represented in its structured
inputs, and an upstream change can make historical inventory evidence stale.
Every adoption action therefore remains a proposal for human review, never an
automatic installation, integration, publication, or claim promotion.
