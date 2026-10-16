# OSS Candidate Compatibility/Adoption Review — 2026-10-16

Status: engineering and adoption review only. Nothing in this document is
scientific evidence, a legal opinion, or a validation of any candidate's
claims. No candidate was cloned, installed, executed, or copied. Source
access date for every fact below: **2026-10-16**, via the GitHub REST API
(`gh api`) and public README content. No repository was downloaded.

Verdicts use this repository's `recommended_action` vocabulary
(`oss_opportunities.validation.ALLOWED_RECOMMENDED_ACTION`):

- `integrate_as_optional_adapter` / `integrate_as_external_tool_record` — direct integration path
- `emulate_architecture_pattern` — workflow/pattern emulation, no code copy
- `create_docs_reference` — reference-only
- `license_review_required` / `security_review_required` / `defer` — blocked pending review
- `reject` — no defensible role here

## Repository baseline

- `origin/main` at review time: `3f3fe8593303184cb88eef056c1322f3d4e57a16`
  (matches the brief's last reviewed SHA).
- Open PR #375 (`grok/batch3-literature-mining-20261016`) proposes a separate
  source registry. It was not edited, and nothing here duplicates it.
- `external_tools/`, `tools/public_repo_harvest/`, and the `oss_opportunities`
  intake/scoring were not replaced. The only change is a set of adoption
  gates inside `oss_opportunities` (see `docs/oss_opportunity_pipeline.md`).

## Candidate table

| Candidate (canonical) | Revision (head at review) | License (GitHub API) | Maintenance / security evidence | Verdict | Role here |
|---|---|---|---|---|---|
| [maziyarpanahi/openmed](https://github.com/maziyarpanahi/openmed) | `0386c53a27951ac51f7a94b3876c69e8e7f84393` (2026-10-14) | Apache-2.0 (SDK). Models: per-model terms, not verified | Not archived; SECURITY.md, NOTICE, CONTRIBUTING present; secret-scanning config present | `reject` | No in-repo clinical free-text path to attach to |
| [ZJU-REAL/PaperGym](https://github.com/ZJU-REAL/PaperGym) | `1ec7fbd2143f1da20e2130f282e61274a7f5174e` (2026-10-15) | MIT | Not archived; LICENSE present; no SECURITY.md | `create_docs_reference` (already applied) | Rubric pattern, already in `docs/research/research_plan_quality_rubric.md` |
| [alphaXiv/OpenResearch](https://github.com/alphaXiv/OpenResearch) | `6285fee7f42bc8ad21500b84278d38679f1ac01b` (2026-10-16) | MIT | Not archived; LICENSE present; desktop installers and managed compute | `emulate_architecture_pattern` | Local-first agent-harness pattern (Awareness Studio agent-harness notes) |
| [morluto/rea](https://github.com/morluto/rea) | `0d224742808e32106e2ee93340c6755ee5e0a0db` (2026-10-16) | MIT | Not archived; SECURITY.md, DISCLAIMER.md present | `reject` | Out of domain; dual-use binary reverse engineering |
| [karpathy/autoresearch](https://github.com/karpathy/autoresearch) | `228791fb499afffb54b46200aca536f79142f117` (2026-03-26) | **none** (GitHub reports no license) | Not archived; no LICENSE file | `license_review_required` | Reference pattern only, until a license is established |

### Namesake and mismatch resolution (verified, not assumed)

- **PaperGym.** The lead `ziu-real/papergym` does not resolve on GitHub
  (404). Namesakes exist (`yunjoochoi/PaperGym`, `cabbagewyh/PaperGym`).
  The canonical project is `ZJU-REAL/PaperGym`. Its README links the arXiv
  paper, the project page, and Hugging Face artifacts, and matches the
  rubric-centered description already cited in this repository.
- **OpenResearch.** The lead `alphaxiv/openresearch` resolves to
  `alphaXiv/OpenResearch` (canonical capitalization).
- **REA ("Reverse Engineer Anything").** The canonical project is
  `morluto/rea`. Its README names it as the official source and warns that
  copied READMEs and similarly named repositories are not official. Several
  unofficial guides and bridges exist (`valorisa/Reverse-Engineer-Anything`,
  `NabilRFG12/Reverse-Engineer-anything`, `Fanqi89/dsh-rea`). Star counts were
  not used as evidence.
- **AutoResearch.** This name is ambiguous. `karpathy/autoresearch` is the
  project that defines the "autoresearch" pattern (fixed-budget autonomous
  experiment loop, keep or discard). Other projects use the same name:
  `EvoMap/AutoResearch` (Apache-2.0), `uditgoenka/autoresearch` (MIT, Claude
  skill), and `aiming-lab/AutoResearchClaw` (MIT). **Open question for the
  owner:** which project was meant? This review treats `karpathy/autoresearch`
  as the canonical pattern source and does not assume the others.

## Per-candidate assessment

### 1. OpenMed — `reject`

- **Capability (README, verified):** clinical NER and PII de-identification
  for clinical text, with local runtimes (Python, MLX, Android, browser),
  2,266 manifest entries, and 35 model-backed PII languages. It is clinical
  NLP, not an EEG or signal-processing library.
- **Defensible use here?** Only if this repository ingested free-text
  clinical notes, and it does not. Its data path is BIDS, EEG/fMRI metadata,
  and derived feature tables. Free-text PII redaction would be a new scope,
  not a gap in the existing pipeline.
- **Blockers if reconsidered:** the README says model downloads, remote
  providers, and telemetry-enabled paths may use the network, and that
  per-model and per-dataset terms must be reviewed. Its model weights are not
  covered by the Apache-2.0 SDK license. The repository forbids clinical
  claims and live APIs in tests, so any clinical-NLP output would carry those
  constraints.
- **Overlap with existing capabilities:** none in `adapters/`,
  `dataset_importers/`, or `external_tools/`.
- **Viable path if the scope ever changes:** a separate, opt-in
  de-identification step over an explicit free-text field, behind an
  `external_tools` record and a security review. Proof test: a fixture with
  synthetic free text, asserting the step is absent from the default pipeline
  and blocked without an explicit flag.

### 2. ZJU-REAL/PaperGym — `create_docs_reference` (already applied)

- **Capability (README, verified):** a data-generation pipeline (arXiv TeX to
  questions and rubrics), a two-stage training scheme (rubric-conditioned
  OPSD, then GRPO with rubric rewards), and an evaluation suite. Released
  artifacts are on Hugging Face (model, PaperGym-20k corpus, benchmarks).
- **Existing overlap:** `docs/research/research_plan_quality_rubric.md`
  already cites "PaperGym's rubric-scoring idea" and applies it as a
  documentation pattern. `tests/research_plan_quality/` exists.
- **Why not direct integration:** the code is a GPU training pipeline (TRL,
  vLLM). Its models and corpus are separate Hugging Face artifacts with
  unverified per-artifact licenses, and the corpus is derived from arXiv papers.
- **Verdict:** reference-only. The rubric pattern is already captured. No new
  code is needed.

### 3. alphaXiv/OpenResearch — `emulate_architecture_pattern`

- **Capability (README, verified):** a local-first harness and workspace for
  research agents. It has a desktop app, a standalone `orx` CLI with a local
  dashboard at `127.0.0.1:4791`, agent skills (`SKILL.md`, `agent-skills/`),
  and a system prompt. Managed compute requires an account.
- **Existing overlap:** `tools/local_agents/research_loop.py` (dry-run-default
  loop with a command allowlist), `command_guard`, and `tools/local_ops`. The
  planner already maps `agent_harness` to "Awareness Studio Agent Harness
  Emulation Notes v1".
- **Why not direct integration:** desktop binaries (macOS, Windows beta,
  AppImage), a Rust codebase, an account-gated managed service
  (`credential_required_execution`), and no Python library surface to adopt.
- **Viable path:** pattern emulation only. Compare the skill-file layout and
  the local-dashboard-first design against Awareness Studio's agent harness,
  and write a design note. Do not copy code. Proof test: a doc-only check that
  the note cites this revision and states the no-copy rule.

### 4. morluto/rea — `reject`

- **Capability (README, verified):** an MCP server and agent workflow for
  reverse engineering applications and native binaries (Hopper and Ghidra
  bridges, runtime analysis).
- **Why reject:** no overlap with a neuroscience simulation or its scientific
  pipelines. The capability is dual-use binary analysis, and this repository's
  scope does not call for it. The README itself stresses that authorization
  context matters, and this project has none for that work.
- **Verdict:** `reject`. No integration path is proposed.

### 5. karpathy/autoresearch — `license_review_required`

- **Capability (README, verified):** a single-GPU nanochat training setup in
  which an agent edits `train.py` in fixed 5-minute runs, keeps or discards
  each result, and repeats. The pattern is driven by a `program.md`
  instruction file.
- **License:** GitHub reports no license, and no LICENSE file exists. This is
  the `missing_high` tier. Copy is blocked (`copy_code_without_license_review`),
  and this review does not treat the project as permissively licensed.
- **Existing overlap:** `tools/local_agents/research_loop.py` already has a
  bounded loop with an allowlist and dry-run default. The fixed-budget,
  keep-or-discard loop is a plausible pattern-level comparison. The GPU
  training code is out of scope for this repository.
- **Viable path:** pattern reference only, and only after the upstream owner
  establishes a license. Do not copy `program.md`, `train.py`, or the nanochat
  dependency. Proof test: a candidate with an empty license string routes to
  `license_review_required` in the planner (covered by the new license tests).

## Existing neuro tools — what is already present

These are not new candidates. Each is already in the repository, so none of
them should be re-proposed as a new adapter or importer.

| Tool | Already present in this repository | Gap, if any |
|---|---|---|
| MNE-Python | `external_tools/registry_seed.json` (`mne-python`); `requirements-eeg.txt` (`mne>=1.4.0`); `data/preprocessing.py` and `dual_engine/data_adapters.py` import `mne` | none identified |
| MNE-BIDS | registry seed (`mne-bids`); `adapters/mne_bids.py` and feature-recipe modules; `requirements-eeg.txt` | the registry records a fuller MNE-BIDS/PyBIDS layout reader as future work (`docs/mne_bids_adapter.md`). This is a real gap, and it is not a new candidate. |
| MOABB | registry seed (`moabb`); `dataset_importers/moabb_importer.py` (metadata only, never downloads) | none; the importer is intentionally metadata-only |
| GUDHI | registry seed (`gudhi`); `requirements-research.txt` (`gudhi>=3.8.0`); `core/topology.py` imports `gudhi` | none identified |
| Ripser | `requirements-base.txt` (`ripser>=0.6.4`); registry seed (`ripser-py`); `core/topological_filtration.py` imports `ripser` | none identified. The optional LGPL `cripser` path in `core/topology.py` is also present. |

## Gaps closed in this change

The batch implemented gates in the existing `oss_opportunities` workflow.
It added no new registry, crawler, or intake. Full detail is in
`docs/oss_opportunity_pipeline.md` ("Adoption gates"):

- **Ambiguous source identity** (`oss_opportunities.validation`): `repo_full_name`
  must be `owner/name`, `owner` must match it, and `repo_url` must point to it.
- **Duplicate candidates** (`oss_opportunities.opportunity_batch`): one repository
  is ranked once. Other observations go to `opportunities_rejected` with a
  `duplicate_of` reason.
- **Unresolved license** (`oss_opportunities.scoring`): an unmatched license
  string now routes to `license_review_required`, the same as an empty one.
- **Unsupported capability claims** (`oss_opportunities.scoring`): adapter-surface
  credit needs a documented surface. A keyword-only category earns half credit.
  This changes scores, not adoption actions, and is a documented limitation.
- **Adoption blocked by unresolved risk** (`oss_opportunities.scoring`): a
  candidate with `requires_credentials` routes to `security_review_required`
  instead of an adapter or tool-record path.

Tests: `tests/test_oss_adoption_gates.py` (synthetic, offline). Test results
are not reported here, because no Python runtime was available in this
environment.
