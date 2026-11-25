# Retrofit inventory — Phase 2 tool-source notes

This note describes the **Phase 2 research registry** only. It classifies
candidate tools that might later sit beside NeuroTopology-Sim as optional
adapters, external records, or explicit non-goals.

It is **not scientific evidence**. It does not validate topology metrics,
does not promote an ontology, and does not claim a theory of consciousness
or a Theory of Everything. License strings are research labels gathered
from public project pages and LICENSE files; they are not a legal opinion.

Source of truth: [`configs/retrofit_inventory/tool_sources.yaml`](../../configs/retrofit_inventory/tool_sources.yaml)

Offline loader: [`tools/retrofit_inventory/tool_sources.py`](../../tools/retrofit_inventory/tool_sources.py)

## Purpose

Phase 1 (Lead) inventories the local checkout. Phase 2 (Research) adds a
fixed, deterministic list of **fifteen** external tool candidates so later
QA / reporting / CLI phases can attach the same ids without inventing
APIs or pulling packages at scan time.

The loader is independent of `build_inventory_snapshot`. It reads local
YAML only. Default output has no mtime or clock fields. Rows are ordered
by `id`.

## Field glossary

| Field | Meaning |
|---|---|
| `id` | Stable slug (`mne`, `scipy-signal`, `notebooklm-mcp`, …). |
| `name` | Display name. |
| `official_source` | Official docs or repository URL only. No invented APIs. |
| `license` | SPDX-ish or license class from a public LICENSE / docs page. Use `unknown` when unverified. |
| `role` | One-line role in a *retrofit* context (adapter / record / non-goal). |
| `integration_mode` | `optional_adapter` \| `external_tool_record` \| `docs_only` \| `experimental` \| `do_not_vendor`. |
| `optional_dependency` | Whether a future adapter would be an optional Python extra. |
| `offline_behavior` | `fully_offline` \| `offline_with_local_data` \| `requires_network` \| `unknown`. |
| `network_risk` / `privacy_risk` | `none` \| `low` \| `medium` \| `high`. |
| `provenance_capability` | What identifiers the tool *can* carry if used later. |
| `adoption_recommendation` | `consider` \| `defer` \| `reject` \| `experimental_only`. |
| `notes` | Caveats. Not a claim that the tool is adopted. |

## Copyleft / vendor policy

GPL / AGPL (and mixed NC) tools must not be vendored into the core tree
without a **human license review**. Prefer `external_tool_record` or
`do_not_vendor`. MATLAB-hosted toolboxes stay external even when a
subset of files is permissively licensed. This registry does not authorize
copying plugin code.

## Offline / test policy

- No live HTTP from this package.
- No dataset downloads.
- No credentials, API keys, or browser logins in tests.
- LSL / BrainFlow tests must not require a live stream or attached board.
- Scrapling must not be used to scrape in tests.
- NotebookLM must not be called.

QA owns `tests/retrofit_inventory/**` and may start Phase 3 validators
against this YAML.

## Per-tool notes

### MNE (`mne`)

MNE-Python is the usual scientific-Python EEG/MEG I/O stack and is already
a declared BSD-3-Clause dependency. `optional_adapter` / `consider` is
appropriate for governed adapters over local files. Official docs:
https://mne.tools/. Not a clinical or consciousness instrument.

### SciPy signal (`scipy-signal`)

`scipy.signal` is BSD-3-Clause numeric code already in `requirements.txt`.
Treat as an `optional_adapter` for filters and spectra with parameter
provenance only. Official docs:
https://docs.scipy.org/doc/scipy/reference/signal.html.

### MNE-Connectivity (`mne-connectivity`)

BSD-3-Clause companion used in-repo for connectivity cross-checks.
`optional_adapter` / `consider`. Official docs:
https://mne.tools/mne-connectivity/. Connectivity numbers are not
ontology or PCI-style evidence.

### EEGLAB (`eeglab`)

MATLAB-ecosystem toolbox. Current `sccn/eeglab` core LICENSE is
BSD-2-Clause; plugins may differ; MATLAB itself is proprietary. Record as
`external_tool_record` and `defer`. Do not vendor. Official site:
https://eeglab.org/.

### FieldTrip (`fieldtrip`)

MATLAB-ecosystem toolbox under GPL-3.0. `external_tool_record` / `defer`.
Never vendor copyleft into core without human review. Official site:
https://www.fieldtriptoolbox.org/.

### LSL (`lsl`)

Lab Streaming Layer (docs: https://labstreaminglayer.readthedocs.io/).
Meta-repo / typical bindings are MIT. Streaming uses local sockets or
multicast — treat as `requires_network` with medium network risk and high
privacy risk (raw biosignals). `optional_adapter` but `defer` until a
gated design exists. Offline tests must not open a live stream.

### BrainFlow (`brainflow`)

MIT device SDK (https://brainflow.org/). Same streaming caveats as LSL:
board/USB/serial/socket paths are network-class risks; privacy risk is
high. `optional_adapter` / `defer`. No live boards in tests.

### PsychoPy (`psychopy`)

GPL-3.0 experiment runner (https://www.psychopy.org/). `do_not_vendor` /
`defer`. External trial logs could be recorded later; do not spawn
PsychoPy or vendor its tree.

### SpikeInterface (`spikeinterface`)

MIT extracellular ephys toolkit
(https://spikeinterface.readthedocs.io/). `optional_adapter` / `consider`
for **local** recording I/O only. No hardware and no downloads in tests.

### NWB (`nwb`)

Neurodata Without Borders format (https://www.nwb.org/). PyNWB/HDMF are
BSD-3-Clause. `optional_adapter` / `consider` for **I/O of already-local
files** only. Do not hit DANDI or S3 from this registry.

### Braindecode (`braindecode`)

Deep-learning EEG library (https://braindecode.org/). Primary license is
BSD-3-Clause; some components are CC-BY-NC-4.0. `optional_adapter` but
`defer` until NC files are enumerated by a human. No training jobs and no
dataset fetches in tests.

### snnTorch (`snntorch`)

MIT spiking-network library (https://snntorch.readthedocs.io/).
`experimental` / `experimental_only`. Numeric research helper only; not a
biological spike claim and not a model of awareness.

### Semantica (`semantica`)

Identified candidate: https://github.com/semantica-agi/semantica (MIT).
Other projects share the name, so identity remains a research choice.
`docs_only` / `defer`. Do not promote ontologies, do not treat graph
nodes as evidence, and do not call live APIs in tests.

### Scrapling (`scrapling`)

Official repo LICENSE is BSD-3-Clause
(https://github.com/D4Vinci/Scrapling). Still `do_not_vendor` / `defer`:
live scraping is forbidden in tests and is not part of the sim retrofit.

### NotebookLM MCP (`notebooklm-mcp`)

**Experimental only.** Official product page:
https://notebooklm.google/. This registry **does not cite an official
supported Google/NotebookLM API or MCP**. Community MCP packages that
drive the hosted UI (browser automation, cookies, unofficial npm
wrappers) are unofficial. Marked `experimental` /
`experimental_only`, license `proprietary` for the hosted service,
`requires_network`, high network and privacy risk. Do not vendor. Do
not log in, do not upload corpora, and do not hit the product from
tests.

## What this file is not

- Not a recommendation to install every listed tool.
- Not a claim that any tool measures experience, PCI, Q, Qabs, or
  f_dress in a theoretically decisive way.
- Not permission to scrape, stream, or call hosted models from CI.
