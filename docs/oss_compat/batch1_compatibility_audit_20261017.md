# Batch 1 — Open-Source Compatibility Audit (2026-10-17)

Status: **HOLD / SYNTHETIC_ONLY**. Audit evidence only. This is not authorization
to adopt, install, import, execute, or copy any candidate, and it is not
scientific validation of any method or tool.

- Base: `origin/main` = `3f3fe8593303184cb88eef056c1322f3d4e57a16` (verified live at audit start)
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
| 4 | [bids-standard/bids-validator](https://github.com/bids-standard/bids-validator) | EEG/BIDS handling | Data standard | MIT | 2026-10-15 | reference only (Node runtime) |
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
- **nibabel, DataLad, Ripser.py: MIT** (COPYING or LICENSE.txt read). GitHub's
  "Other" label reflects file layout, not a non-MIT license.
- **DataLad runtime:** git-annex (GPL-3.0) is a separate external dependency.
- **SimNIBS and pyspi: GPL-3.0** (GitHub API and README). External-process use
  only, with no in-process import.
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
- **persim** (`dual_engine/spectral_tda.py`, `analysis/connectivity_topology.py`,
  `tools/tda_reproducibility/equivalence.py`).
- **nibabel** (`requirements-research.txt`; 10 Python modules import it).
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

- `docs/oss_compat/compatibility_inventory_20261017.json` parsed as valid JSON.
- Consistency rules were executed with Node.js (`node -e`). The rules mirror the
  Python test: head-SHA format, canonical URL, vocabularies, the license gate on
  integration, the copy restriction on restricted licenses, no workflow tools as
  runtime dependencies, the stale-repository exclusion, existing-dependency
  overlap, out-of-scope rejection, and the named-lead set. **Result: 23 candidates,
  all rules pass.**
- `tests/oss_compat/test_compatibility_inventory.py` (11 tests) was written to the
  same rules. **It was not executed:** this environment has no Python runtime, and
  no interpreter was installed. Run `pytest tests/oss_compat -q` before merge.

## 9. Changed paths

- `docs/oss_compat/batch1_compatibility_audit_20261017.md` (new; this report)
- `docs/oss_compat/compatibility_inventory_20261017.json` (new)
- `tests/oss_compat/test_compatibility_inventory.py` (new)

No other path changed. Not touched: PR #375, PR #391, `external_tools/`, and
`tools/public_repo_harvest/`.

## 10. Pull request

Recorded in the session handoff.
