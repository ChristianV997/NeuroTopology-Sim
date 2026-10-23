# Batch 1 — Open-Source Compatibility Audit (2026-10-17)

Status: **HOLD / SYNTHETIC_ONLY**. Audit evidence only. This is not authorization
to adopt, install, import, execute, or copy any candidate, and it is not
scientific validation of any method or tool.

- Base (historical audit start): `origin/main` = `3f3fe8593303184cb88eef056c1322f3d4e57a16`
- Base (branch sync, 2026-10-23): `origin/main` = `57b7e43d42678822e9eec03679891c1770040327` (inventory `base_main_sha`)
- Branch: `batch1/claude-d-oss-compatibility-map`
- Research date (UTC): **2026-10-17**
- Machine-readable inventory: `docs/oss_compat/compatibility_inventory_20261017.json`
- Consistency tests: `tests/oss_compat/test_compatibility_inventory.py`

Method: GitHub REST API for repository metadata, head commit, latest release, and
license metadata. LICENSE and COPYING files were read as text where noted. README
excerpts were read for capability claims. No repository was cloned, installed,
imported, executed, or copied, and no dataset was downloaded.

## 1. Compatibility matrix

Dispositions use the five labels from the brief. Each candidate gets exactly one.

| # | Candidate (canonical) | Need area | Role | License (verified) | Last commit | Disposition |
|---|---|---|---|---|---|---|
| 1 | [mne-tools/mne-python](https://github.com/mne-tools/mne-python) | EEG/BIDS handling | Scientific runtime | BSD-3-Clause | 2026-10-15 | integrate behind bounded adapter (existing use) |
| 2 | [mne-tools/mne-bids](https://github.com/mne-tools/mne-bids) | EEG/BIDS handling | Data standard | BSD-3-Clause | 2026-10-16 | integrate behind bounded adapter |
| 3 | [NeuroTechX/moabb](https://github.com/NeuroTechX/moabb) | EEG/BIDS (benchmarks) | Data standard | BSD-3-Clause | 2026-10-16 | integrate behind bounded adapter (metadata only) |
| 4 | [bids-standard/bids-validator](https://github.com/bids-standard/bids-validator) | EEG/BIDS handling | Data standard | MIT | 2026-10-15 | reference only (Deno runtime) |
| 5 | [openmeeg/openmeeg](https://github.com/openmeeg/openmeeg) | Forward model | Scientific runtime | CeCILL-B (LICENSE read) | 2026-10-13 | integrate behind bounded adapter, **after license review** |
| 6 | [simnibs/simnibs](https://github.com/simnibs/simnibs) | Forward model (TMS/TES) | Scientific runtime | GPL-3.0 | 2026-03-03 | reference only |
| 7 | [mne-tools/mne-connectivity](https://github.com/mne-tools/mne-connectivity) | Signal processing | Scientific runtime | BSD-3-Clause | 2026-10-12 | integrate behind bounded adapter |
| 8 | [nipy/nibabel](https://github.com/nipy/nibabel) | EEG/BIDS (imaging I/O) | Data standard | MIT (COPYING read) | 2026-10-16 | integrate behind bounded adapter (existing use) |
| 9 | [netneurolab/neuromaps](https://github.com/netneurolab/neuromaps) | Surrogates | Scientific runtime | **CC BY-NC-SA 4.0** (LICENSE read) | 2026-06-04 | reference only |
| 10 | [netneurolab/netneurotools](https://github.com/netneurolab/netneurotools) | Surrogates | Reference method | BSD-3-Clause | 2026-07-31 | emulate narrow pattern |
| 11 | [neurolib-dev/neurolib](https://github.com/neurolib-dev/neurolib) | Synthetic generators | Scientific runtime | MIT | **2024-12-18 (stale)** | reject or defer |
| 12 | [DynamicsAndNeuralSystems/pyspi](https://github.com/DynamicsAndNeuralSystems/pyspi) | Surrogates / validation | Scientific runtime | GPL-3.0 | 2026-10-13 | reject or defer |
| 13 | [scikit-tda/persim](https://github.com/scikit-tda/persim) | Topology | Scientific runtime | MIT | 2026-08-27 | integrate behind bounded adapter (existing use) |
| 14 | [scikit-tda/ripser.py](https://github.com/scikit-tda/ripser.py) | Topology | Scientific runtime | MIT (LICENSE.txt read) | 2026-08-03 | integrate behind bounded adapter (existing use) |
| 15 | [GUDHI/gudhi-devel](https://github.com/GUDHI/gudhi-devel) | Topology | Scientific runtime | MIT | 2026-10-12 | integrate behind bounded adapter (existing use) |
| 16 | [giotto-ai/giotto-tda](https://github.com/giotto-ai/giotto-tda) | Topology | Scientific runtime | AGPL-3.0, dual-licensed (LICENSE read) | **2024-05-30 (stale)** | reject or defer |
| 17 | [datalad/datalad](https://github.com/datalad/datalad) | Research reproducibility | Workflow tool | MIT (COPYING read); git-annex is GPL-3.0 | 2026-10-14 | reference only |
| 18 | [treeverse/dvc](https://github.com/treeverse/dvc) | Research reproducibility | Workflow tool | Apache-2.0 | 2026-08-06 | reference only |
| 19 | [maziyarpanahi/openmed](https://github.com/maziyarpanahi/openmed) | Out of scope (clinical NLP) | Out-of-domain tool | Apache-2.0 SDK; model terms unverified | 2026-10-16 | reject or defer |
| 20 | [ZJU-REAL/PaperGym](https://github.com/ZJU-REAL/PaperGym) | Research-agent workflow | Workflow tool | MIT | 2026-10-15 | reference only |
| 21 | [alphaXiv/OpenResearch](https://github.com/alphaXiv/OpenResearch) | Research-agent workflow | Workflow tool | MIT (LICENSE read) | 2026-10-16 | emulate narrow pattern |
| 22 | [morluto/rea](https://github.com/morluto/rea) | Out of scope (dual-use binary RE) | Out-of-domain tool | MIT | 2026-10-17 | reject or defer |
| 23 | [karpathy/autoresearch](https://github.com/karpathy/autoresearch) | Research-agent workflow | Workflow tool | **none** | 2026-03-26 | reference only |

Disposition counts: integrate behind bounded adapter 9; emulate narrow pattern 2;
reference only 7; reject or defer 5; copy pattern after review 0.

The "copy pattern after review" disposition is not used by any candidate. No
candidate has a permissive license plus a reviewed pattern that needs more than
an adapter or emulation.

## 2. Research-agent workflow tools vs scientific runtime dependencies

These two groups must not be conflated. Rows 17–18 and 20–23 are workflow tools
for research agents and reproducibility. They do not provide EEG data, forward
models, surrogates, or topology, and their outputs are not validation evidence.
Putting them into a scientific runtime would add dependencies that cannot
improve scientific credibility.

- **Workflow tools** (PaperGym, OpenResearch, AutoResearch, DataLad, DVC): useful as
  patterns for agent loops, dashboards, skill files, and dataset provenance.
  Dispositions are reference-only or emulate. None is a runtime dependency.
- **Scientific runtimes and standards** (MNE, MNE-BIDS, MOABB, OpenMEEG, nibabel,
  persim, Ripser, GUDHI): carry computational or data-standard weight. They need
  pinned revisions, license review where the license is not permissive, and
  fixture-only tests.
- **Out-of-domain** (OpenMed, REA): not part of any scientific need here.

PaperGym, AutoResearch, OpenResearch, and REA are not EEG datasets, and none of
them is validation evidence for this project's claims.

## 3. Named leads: verification details

| Lead as given | Resolved canonical | Verification |
|---|---|---|
| `maziyarpanahi/openmed` | same | Repo and README read. It is clinical NER and PII de-identification for clinical text, not an EEG or BIDS library. Apache-2.0 SDK. README states model downloads, remote providers, and telemetry may use the network. Not a fit for EEG. |
| `ziu-real/papergym` | `ZJU-REAL/PaperGym` | The lead owner does not resolve (404). Canonical is MIT, rubric-centered research-plan generation with GPU training. Namesakes exist (`yunjoochoi/PaperGym`, `cabbagewyh/PaperGym`). |
| `alphaxiv/openresearch` | `alphaXiv/OpenResearch` | Case-insensitive match. MIT. Local-first research-agent harness with desktop app, CLI, and skill files. |
| REA ("Reverse Engineer Anything") | `morluto/rea` | README says it is the official source and warns that similarly named repositories are unofficial. MIT. Binary reverse engineering. |
| AutoResearch | `karpathy/autoresearch` (assumed) | **Ambiguous.** Other projects share the name: `EvoMap/AutoResearch` (Apache-2.0), `uditgoenka/autoresearch` (MIT), `aiming-lab/AutoResearchClaw` (MIT). The karpathy repo defines the pattern and has no license. The owner must confirm which one is meant. |

Note on earlier pins: PR #386 (`docs/oss_opportunity_candidate_review_20261016.md`)
pinned OpenMed at `0386c53…` and REA at `0d22474…`. Both heads have moved. This
audit pins the current heads, listed in the inventory. The earlier review's
dispositions are unchanged.

## 4. License evidence and uncertainty

GitHub's license label is a starting point, not a verdict. Where the label and the
text disagree or the label is "Other", the LICENSE file was read.

- **OpenMEEG: CeCILL-B.** GitHub reports "Other". The LICENSE text says CeCILL-B,
  GPL-compatible, with an attribution duty. This repository's license classifier
  does not recognize CeCILL-B and fails closed. Adoption therefore requires a
  license review decision.
- **neuromaps: CC BY-NC-SA 4.0.** The LICENSE file applies non-commercial and
  ShareAlike terms to the repository. This conflicts with copying or
  redistributing it in a project not established as non-commercial. Reference
  only.
- **giotto-tda: AGPL-3.0, dual-licensed.** The LICENSE file states AGPL with a
  commercial-licence contact. GitHub reports "Other". Copyleft applies unless a
  commercial licence is obtained.
- **nibabel, DataLad, Ripser.py: MIT main license** (COPYING or LICENSE.txt read).
  GitHub's "Other" label reflects file layout, not a non-MIT license. For nibabel
  and DataLad the MIT statement covers the project's own code only: both COPYING
  files also list bundled third-party code or data under other terms (see
  section 12), so the MIT label is not a component-level clearance.
- **DataLad runtime:** git-annex (GPL-3.0) is a separate external dependency.
- **SimNIBS and pyspi: GPL-3.0** (GitHub API and README; pyspi's README says
  "or later" in one place and plain GPL elsewhere, so "or later" is not relied
  on). External-process use only, with no in-process import.
- **OpenMed models:** the SDK is Apache-2.0, but model artifacts carry per-model
  terms that were not verified. Unresolved.
- **AutoResearch: no license.** No copy is permitted.
- Other permissive labels (MIT, BSD-3-Clause, Apache-2.0) were taken from GitHub's
  SPDX metadata. Their LICENSE files were not separately read in this audit.

Per the brief, a license label does not itself prove compatibility. Unresolved
licensing stays unresolved.

## 5. Existing overlap in this repository

Already present and not re-proposed as new work:

- **MNE-Python** (`requirements-eeg.txt`, `data/preprocessing.py`,
  `dual_engine/data_adapters.py`, registry seed).
- **MNE-BIDS** (`adapters/mne_bids.py` and feature-recipe modules, registry seed,
  which notes a fuller layout reader as future work). This is the main real gap in
  the EEG/BIDS area.
- **MOABB** (`dataset_importers/moabb_importer.py`, metadata only).
- **GUDHI** (`core/topology.py`, `requirements-research.txt`).
- **Ripser** (`core/topological_filtration.py`, `requirements-base.txt`).
- **persim** (`requirements-base.txt`, `persim>=0.3.1`; the only code that
  imports it is the optional path in `tools/tda_reproducibility/equivalence.py`.
  `dual_engine/spectral_tda.py` and `analysis/connectivity_topology.py` use
  ripser, not persim).
- **nibabel** (`requirements-research.txt`, `nibabel>=5.1.0`; imported by several
  modules, for example `validation/montage_topology.py`).
- **mne-connectivity** (`requirements-eeg.txt`; in-house Kuramoto and LEiDA
  comparators overlap with it).
- **Null-control surrogate scaffold** (phase-randomized, channel-shuffled, and
  time-reversed surrogates). This is the existing home for neuromaps and
  netneurotools patterns.

## 6. Source-harvest and PR coordination

`tools/public_repo_harvest/` already contains `license_scanner.py`,
`source_repo_registry.py`, `compatibility_patch_plan.py`,
`external_systems_scorecard.py`, and `reusable_pattern_registry.py`. Open PR #391
modifies several of these and adds `source_pack.py`. Open PR #375 adds
`configs/research/batch3_source_registry.yaml`.

This audit touches none of those paths. It is a separate, dated artifact under
`docs/oss_compat/`. It does not replace the harvest tools or the external-tools
registry, and it does not create a crawler or intake. The `license_scanner` on
main is a string match, which is cruder than the classifier in
`oss_opportunities`. This report does not replace either one.

## 7. Unresolved risks

1. **OpenMEEG license** (CeCILL-B) is outside the classifier. Needs a human decision before any adapter.
2. **Stale repositories:** neurolib (last commit 2024-12-18) and giotto-tda (2024-05-30). Maintenance evidence is weak.
3. **neuromaps non-commercial terms** may block any reuse.
4. **OpenMed model terms** and network behaviour unverified. Irrelevant to EEG but relevant if ever reconsidered.
5. **AutoResearch ambiguity:** which project is meant, and whether any license exists.
6. **Dual-use REA** should stay out of scope. The README stresses authorization.
7. **PaperGym's artifacts** (Hugging Face models and corpus) carry separate, unverified licenses. Not relevant to any adopted path.
8. **DataLad** pulls in GPL-3.0 git-annex and dataset fetches, which the no-download guardrail forbids.
9. **Speculative, not demonstrated:** netneurotools connectome nulls and pyspi comparators are plausible validation aids. They are labelled speculative and have no demonstrated fit yet.

## 8. Tests and outputs

- `docs/oss_compat/compatibility_inventory_20261017.json` parses as valid JSON
  (23 candidates; row IDs unchanged).
- `tests/oss_compat/test_compatibility_inventory.py` holds 25 pytest tests: the
  original 15 rules plus 10 source-backed field checks added in section 12.
  Run `python -m pytest tests/oss_compat -q -o addopts= --override-ini=required_plugins= --confcutdir=.`.
  These are artifact-consistency checks; they do not install, import, or execute
  any candidate and are not scientific validation.

## 9. Changed paths

- `docs/oss_compat/batch1_compatibility_audit_20261017.md` (new; this report)
- `docs/oss_compat/compatibility_inventory_20261017.json` (new)
- `tests/oss_compat/test_compatibility_inventory.py` (new)

No other path changed. Not touched: PR #375, PR #391, `external_tools/`, and
`tools/public_repo_harvest/`.

## 10. Pull request

Recorded in the session handoff.

## 11. Release and package-license revalidation — 2026-10-22

The matrix and repository-head fields above describe the 2026-10-17 snapshot;
they are not silently rewritten as if observed on this later date. The
machine-readable inventory now records a separate release revalidation date,
exact tag refs, release dates, and resolved commit objects for the four rows
whose release records changed or whose tag spelling needed correction:

| Inventory row | Revalidated release | Published | Resolved commit |
|---|---|---|---|
| `openresearch` | [`v0.2.20`](https://api.github.com/repos/alphaXiv/OpenResearch/releases/tags/v0.2.20) | 2026-10-21 | `37a367bcdbc26ba2a492bccf12b85bddc5852567` |
| `rea` | [`rea-agents-6.7.0`](https://api.github.com/repos/morluto/rea/releases/tags/rea-agents-6.7.0) | 2026-10-18 | `27dc42d10249f0410904a75c0997842eb03b931c` |
| `persim` | [`v0.4.1`](https://api.github.com/repos/scikit-tda/persim/releases/tags/v0.4.1) | 2026-10-18 | `00144a82949c214283655f68d1985725882eea59` |
| `gudhi` | [`tags/gudhi-release-3.13.0`](https://api.github.com/repos/GUDHI/gudhi-devel/git/ref/tags/tags/gudhi-release-3.13.0) | 2026-07-02 | `5dbe510bed5d8d700ec7243fd915769fb67964a2` |

For GUDHI, the literal upstream tag name itself contains the prefix `tags/`;
the verified Git ref is `refs/tags/tags/gudhi-release-3.13.0`. The GitHub root
license label and repository `LICENSE` text are MIT evidence at repository
scope only. PyPI's 3.13.0 JSON metadata has no declared `license` or
`license_expression`; official [GUDHI licensing guidance](https://gudhi.inria.fr/licensing/)
describes MIT library code while warning that some modules/dependencies use
GPLv3/LGPL components (including CGAL, Miniball, and PyKeOps). Therefore the
inventory now requires both `license_review` and
`module_specific_dependency_scope_review`; it does not assert blanket package
or transitive-license clearance. Evidence also includes the pinned [root
LICENSE](https://github.com/GUDHI/gudhi-devel/blob/1c4ba125edf2822f823fb6669cfac067dafd10d7/LICENSE),
[PyPI project](https://pypi.org/project/gudhi/3.13.0/), and
[PyPI metadata](https://pypi.org/pypi/gudhi/3.13.0/json) and
[exact GitHub release record](https://api.github.com/repos/GUDHI/gudhi-devel/releases/tags/tags/gudhi-release-3.13.0).

Persim's package-level statement is recorded separately from GitHub's
repository label: the [PyPI 0.4.1 project metadata](https://pypi.org/project/persim/0.4.1/)
declares the OSI Approved MIT License classifier. That statement is limited to
the package metadata inspected; it does not imply transitive/component
licensing or compatibility.

This revalidation used public GitHub Releases/tag-ref and PyPI metadata plus
official GUDHI licensing guidance. No candidate was cloned, installed,
imported, executed, or copied; no datasets were accessed. Version and license
records are evidence snapshots, not adoption approval, security certification,
legal clearance, compatibility conclusions, or scientific evidence. The
initial `head_sha` and `last_commit_utc` values remain explicitly historical
and require a separate revalidation before they are treated as current.

## 12. Package, version, license, and overlap field revalidation — 2026-10-23

Sources: PyPI JSON metadata (`https://pypi.org/pypi/<name>/json`), LICENSE/COPYING
text and tag refs fetched read-only from `raw.githubusercontent.com` at pinned
tags or commits, and in-repo greps. The GitHub REST API was not reachable in this
session, so GitHub release records (`published_utc`) were not re-read and keep the
2026-10-22 values. No candidate was cloned, installed, imported, or executed.

Row-level changes (IDs unchanged):

| Row | Change | Evidence |
|---|---|---|
| `persim` | `maintenance_signal` said the latest tagged release was 2025-03-12, contradicting `latest_release` v0.4.1 (2026-10-18). Corrected. `existing_overlap` cited two modules that use ripser, not persim; now cites `requirements-base.txt` and the one optional import in `tools/tda_reproducibility/equivalence.py`. License evidence URL added (pinned `LICENSE.txt`, MIT text). | PyPI upload 2026-10-18; repo greps; raw LICENSE.txt at the v0.4.1 commit |
| `nibabel` | Newer tag/package 5.4.2 exists (PyPI 2026-03-11); the 5.4.1 release record is kept and flagged. Package license metadata added (MIT expression). `component_license_caveat` added for the COPYING "3rd party code and data" section (NetCDF/SciPy, Sphinx extension, OrderedSet, MNI template, Philips PAR/REC under PDDL). Unsupported "10 Python modules" count removed. | PyPI JSON 5.4.2; raw COPYING at tag 5.4.2 |
| `datalad` | Package license metadata added; `component_license_caveat` added (COPYING lists parts under Python, BSD-2, BSD-3 licenses; git-annex stays a separate GPL-3.0 tool). | PyPI JSON 1.7.1; raw COPYING at tag 1.7.1 |
| `neurolib` | GitHub tag v0.7.0 has no PyPI release; PyPI latest is 0.6.2 (2022). Recorded as `package_channel_note` so a tag is not read as an installable version. | PyPI JSON; raw LICENSE at v0.7.0 |
| `bids-validator` | GitHub 3.0.2 is the Node validator; the PyPI project of the same name (1.14.7.post0) is a different artifact. `package_channel_note` added; no `package_version` recorded. (Superseded by section 14: tag 3.0.2 is a Deno validator and the matching PyPI package is `bids-validator-deno`.) | PyPI JSON |
| `giotto-tda` | PyPI license field "GNU AGPLv3" recorded as package metadata. | PyPI JSON 0.6.2 |
| `neuromaps` | PyPI metadata conflicts with itself (NonCommercial license text vs a BSD classifier). Recorded as `conflicting_pypi_metadata`, not resolved; disposition and `non_commercial_conflict` status unchanged. | PyPI JSON 0.0.7 |
| `gudhi` | Missing `package_license_evidence_url` added (PyPI JSON). | PyPI JSON 3.13.0 |
| `pyspi` | "GPL-3.0 or later (README and API)" overstated the evidence; the API/PyPI say GPL v3 and the README is inconsistent on "or later". | raw README at v2.0.2 |
| 10 rows | `license_evidence_url` was null for mne-python, mne-bids, moabb, bids-validator, simnibs, netneurotools, neurolib, mne-connectivity, dvc, pyspi; each now cites its LICENSE file at the pinned `head_sha` (headers read; they match the recorded licenses). | raw LICENSE at head_sha |

What these fields do and do not establish. A license field, classifier, or file
header is a declaration by the project about itself. It is not a transitive
license scan, a security review, a maintenance judgment, a compatibility
finding, legal clearance, or evidence of scientific suitability; each of those is
a separate question this inventory leaves open. Dispositions are unchanged.

## 13. Provenance regressions and cross-PR consistency — 2026-10-23 (Agent D)

Primary sources re-fetched read-only (PyPI JSON; GUDHI upstream LICENSE and
https://gudhi.inria.fr/licensing/; GitHub Releases/tag-ref API). No candidate
was cloned, installed, imported, or executed. Claude Agent C’s read-only source
report was not available in this workspace; findings below are from this agent’s
own fetches.

Row-level changes in this pass (stable IDs and dispositions unchanged):

| Row | Change | Evidence |
|---|---|---|
| `gudhi` | `evidence_urls` cited bare-tag API paths (`…/gudhi-release-3.13.0`) that return HTTP 404. Replaced with the literal upstream tag paths used in `latest_release` (`…/tags/gudhi-release-3.13.0`). | GitHub API 200 vs 404 probe, 2026-10-23 |
| `gudhi` | `license_spdx_or_text` and `component_license_caveat` now state per-module licensing is unresolved and legal compatibility is not assessed (aligned with merged #375 `license_scope`, without changing this inventory’s `integrate_behind_bounded_adapter` disposition). | Upstream licensing page; #375 `configs/research/batch3_source_registry.yaml` at merge commit `2c8a80bf` |
| meta | `base_main_sha` refreshed from historical `3f3fe859…` to live main `57b7e43d…` after a normal merge. Snapshot `retrieval_date_utc` / head fields remain 2026-10-17 historical. | `git rev-parse origin/main` |

Cross-PR consistency (read-only; no edits outside owned paths):

| Artifact | Observation | Action |
|---|---|---|
| #375 (merged) GUDHI | Pin `tags/gudhi-release-3.13.0` / package 3.13.0; classification **EMULATE**; per-module licensing **unresolved**. | Pins and unresolved scope preserved here. Disposition disagreement (#375 EMULATE vs #406 integrate) kept visible; not collapsed. |
| #386 (open) | Documents stable IDs `openmed`, `papergym`, `openresearch`, `rea`, `autoresearch`, plus `gudhi` caveat; does not duplicate versions/licenses. | All six IDs present; full 23-row ID set locked by regression tests. #386 paths not edited. |
| #443 (open) | Maps `oss_compatibility_inventory_artifact` → `tests/oss_compat/test_compatibility_inventory.py`. Mapping not on main yet. | Workflows not edited; mapping packet left for Codex Agent A. |

Regression tests added for HTTPS evidence URLs, stable ID set, GUDHI literal-tag
evidence URLs, explicit unresolved language, #375 pin alignment, `base_main_sha`
format/citation, and neuromaps conflict non-clearance.

## 14. Independent row audit, link resolution, and cross-registry check — 2026-10-23 (Agent B)

Scope: all 23 rows re-read against upstream release/tag records, package metadata, and license files. Nothing was cloned, installed, imported, or executed. This section is evidence bookkeeping and does not certify any package.

How URLs were checked. `github.com/<repo>/blob/<ref>/<path>` evidence URLs were resolved through `raw.githubusercontent.com` at the same ref, and `pypi.org` URLs directly: every one returned HTTP 200 on 2026-10-23 (no URL that could be resolved failed). `api.github.com` release and tag-ref URLs, repository and releases pages on `github.com`, and `gudhi.inria.fr` could not be resolved by that method; the GitHub releases pages for openmed, openresearch, rea, bids-validator, simnibs, openmeeg, and neurolib were read through a web fetch instead. A resolving URL shows only that a file or record exists at that ref.

Defects reproduced and what changed (IDs and dispositions unchanged):

| Row | Finding | Source | Change |
|---|---|---|---|
| `bids-validator` | The row called tag 3.0.2 a TypeScript/Node package. The tag's `deno.json` names `@bids/validator` 3.0.2 and its README runs `deno run -ERWN jsr:@bids/validator`. The PyPI project that tracks it is `bids-validator-deno` 3.0.2 (license expression MIT), not the older `bids-validator` 1.14.x. | raw `deno.json` and README at tag 3.0.2; PyPI JSON for `bids-validator-deno` | Runtime, rationale, and channel note corrected to Deno; wrapper package fields added; wrapper contents recorded as not inspected. |
| `openresearch` | The GitHub releases page marks v0.2.21 (2026-10-23) Latest; the snapshot says v0.2.20 (2026-10-21). | GitHub releases page, read 2026-10-23 | `newer_release_observed` added (not a pin; tag ref and commit unresolved). The v0.2.20 snapshot is unchanged. |
| `gudhi` | Re-confirmed that bare-tag paths return HTTP 404 and the literal tag `tags/gudhi-release-3.13.0` returns 200; tag and commit `5dbe510b` serve identical `LICENSE` and `CMakeLists.txt`. | raw requests at the tag, the bare tag, and the commit | None needed; a regression now locks the literal-tag form. Per-module licensing stays unresolved. |
| `neuromaps` | Re-confirmed: the `LICENSE` file at the pinned head is CC BY-NC-SA 4.0 text, PyPI 0.0.7 carries the same text in its license field, and its classifier says BSD. | raw `LICENSE`; PyPI JSON | None; the conflict stays recorded and unresolved. |
| top level | No machine-readable record of where this inventory differs from the merged #375 registry, or of which URL classes were not resolved. | #375 `configs/research/batch3_source_registry.yaml` at current main | Added `cross_registry_notes` and `link_resolution_scope`. |

Comparison with #375 (read only, not edited, verdicts not copied). Overlapping sources: mne-python, mne-bids, bids-validator, mne-connectivity, gudhi, ripser, datalad, neurolib, rea. Versions agree for all but REA: #375 records `rea-agents-6.5.0` (2026-10-14) while the releases page marks `rea-agents-6.7.0` (2026-10-18) Latest, which this inventory records. #375 names the project `ripser-py`; this inventory's stable id `ripser.py` is kept. Classification differences are not reconciled here: GUDHI is EMULATE in #375 and `integrate_behind_bounded_adapter` here; Ripser is EMULATE there and integrate here. #375 covers 16 sources and this inventory 23; the rest do not overlap.

Per-row summary (release is the recorded GitHub tag; package is the PyPI version where a package record exists):

| Row | Release tag | Package | License status / evidence level | Disposition |
|---|---|---|---|---|
| `openmed` | v3.0.0 | - | permissive / license_file_text | `reject_or_defer` |
| `papergym` | none | - | permissive / github_api_spdx | `reference_only` |
| `openresearch` | v0.2.20 | - | permissive / license_file_text | `emulate_narrow_pattern` |
| `rea` | rea-agents-6.7.0 | - | permissive / github_api_spdx | `reject_or_defer` |
| `autoresearch` | none | - | missing / github_api_spdx | `reference_only` |
| `mne-python` | v1.13.2 | - | permissive / github_api_spdx | `integrate_behind_bounded_adapter` |
| `mne-bids` | v0.20.0 | - | permissive / github_api_spdx | `integrate_behind_bounded_adapter` |
| `moabb` | v1.7.2 | - | permissive / github_api_spdx | `integrate_behind_bounded_adapter` |
| `bids-validator` | 3.0.2 | 3.0.2 | permissive / github_api_spdx | `reference_only` |
| `openmeeg` | 2.6.0 | - | permissive_custom_review_required / license_file_text | `integrate_behind_bounded_adapter` |
| `simnibs` | v4.6.0 | - | copyleft_strong / github_api_spdx | `reference_only` |
| `neuromaps` | 0.0.7 | 0.0.7 | non_commercial_conflict / license_file_text | `reference_only` |
| `netneurotools` | 0.3.0 | - | permissive / github_api_spdx | `emulate_narrow_pattern` |
| `neurolib` | v0.7.0 | 0.6.2 | permissive / github_api_spdx | `reject_or_defer` |
| `mne-connectivity` | v0.9.0 | - | permissive / github_api_spdx | `integrate_behind_bounded_adapter` |
| `nibabel` | 5.4.1 | 5.4.2 | permissive / license_file_text | `integrate_behind_bounded_adapter` |
| `datalad` | 1.7.1 | 1.7.1 | permissive / license_file_text | `reference_only` |
| `dvc` | 3.67.1 | - | permissive / github_api_spdx | `reference_only` |
| `pyspi` | v2.0.2 | - | copyleft_strong / github_api_spdx | `reject_or_defer` |
| `persim` | v0.4.1 | 0.4.1 | permissive / license_file_text | `integrate_behind_bounded_adapter` |
| `ripser.py` | v0.6.15 | - | permissive / license_file_text | `integrate_behind_bounded_adapter` |
| `gudhi` | tags/gudhi-release-3.13.0 | 3.13.0 | permissive_custom_review_required / upstream_license_page_and_pypi_metadata | `integrate_behind_bounded_adapter` |
| `giotto-tda` | v0.6.2 | 0.6.2 | dual_licensed_copyleft / license_file_text | `reject_or_defer` |

Limits. Legal clearance, transitive and per-module licensing, security posture, maintenance quality, compatibility with this repository, data access, and scientific suitability are all outside what a package declaration or license file can show, and none is claimed.
