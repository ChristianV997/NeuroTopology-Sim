# Research tooling matrix

Review date: 2026-09-05
Inspected base: `62637a4b9c82c0c258bfc49e28dee1af757b1c25` (`origin/main`)
Machine-readable source: `configs/tool_admission/tool_registry.yaml`

This matrix is an admission ledger, not a scientific result. No cell is a
`PASS` on a hypothesis. `K > 100` remains owned by
`sim/pitnn/bayesian_falsification.py`.

## Decision rule

| Mode | Meaning |
|---|---|
| integrate | May be imported by optional or declared Python paths |
| emulate | Live/hardware surface only; tests use fixtures |
| copy_pattern | Reuse a schema or log format; do not depend on the package |
| reference | Read algorithms/docs; no runtime dependency |
| reject | Must not be imported, fetched, or required |

## Matrix

| id | tool | mode | admission_status | optional | offline tests | streaming | modalities | license | in requirements.txt |
|---|---|---|---|---|---|---|---|---|---|
| mne | MNE-Python | integrate | admitted | no (core EEG) | fixture only | no | EEG/MEG/iEEG | BSD-3-Clause | yes |
| mne_connectivity | MNE-Connectivity | integrate | admitted_optional | yes | fixture only | no | EEG/MEG/iEEG | BSD-3-Clause | yes |
| scipy_signal | SciPy signal | integrate | admitted | no (core) | yes | n/a | arrays | BSD-3-Clause | yes |
| eeglab | EEGLAB | reference | reference_only | MATLAB only | no MATLAB in CI | no | EEG/MEG | BSD-style | no |
| fieldtrip | FieldTrip | reference | reference_only | MATLAB only | no MATLAB in CI | buffer out of scope | M/EEG/iEEG | GPL-3.0 | no |
| labstreaminglayer | LabStreamingLayer | emulate | admitted_optional | yes | no sockets | yes | EEG + markers | MIT | no |
| brainflow | BrainFlow | emulate | admitted_optional | yes | no boards | yes | EEG/EMG/ECG | MIT | no |
| psychopy | PsychoPy | copy_pattern | deferred | not a dep | no GUI | markers via LSL | behavior | GPL-3.0 | no |
| spikeinterface | SpikeInterface | reference | admitted_optional | yes | no downloads | limited | extracellular ephys | MIT | no |
| pynwb | NWB/PyNWB | integrate | admitted | archival path | local NWB only | lazy HDF5 | ephys/NWB | BSD-3-Clause | yes |
| braindecode | Braindecode | reference | deferred | yes | no fetchers | no | EEG decode | BSD-3-Clause | no |
| snntorch | snnTorch | reference | deferred | yes | no import | no | tensors | MIT | no |
| semantica | Semantica | reference | deferred | studio only | no LLM | no | documents | MIT | no |
| scrapling | Scrapling | reject | rejected | n/a | parser fixtures only | n/a | HTML | BSD-3-Clause | no |
| notebooklm_mcp_community | NotebookLM community MCP | reference | experimental | forbidden required | no | chat only | notes | NOASSERTION | no |
| gemini_notebook_enterprise_api | Gemini Notebook Enterprise API | reference | deferred | forbidden required | no | no | enterprise docs | Apache-2.0 clients | no |

## Binding policies

1. Community NotebookLM MCP servers are `experimental` and unofficial.
2. Internal/private APIs are not required dependencies.
3. Scrapling stays rejected unless a human allowlists a public source in
   `source_registry.json` and a later work order changes the mode.
4. EEGLAB and FieldTrip are MATLAB reference tools, not Python dependencies.
5. SpikeInterface is extracellular electrophysiology only.
6. Braindecode and snnTorch cannot write scientific verdicts.
7. MNE and SciPy signal are the core signal path.
8. NWB/PyNWB is the archival interchange path.
9. LSL and BrainFlow are optional live acquisition boundaries.
10. Tests in `tests/tool_admission/` perform no network I/O.

## Inspected repository anchors

- `AGENTS.md` — no clinical claims, no ontology promotion, no live APIs in tests
- `CLAUDE.md` — dual system (sim engine + Awareness Studio)
- `requirements.txt` — already declares mne, mne-connectivity, scipy, pynwb
- `governance/spec.py` — HypothesisSpec claim types M/K/C
- `sim/pitnn/empirical_pipeline.py` — SciPy butter/hilbert path
- `apps/awareness_studio/TOOLS_MANIFEST.md` — tools default off, no MCP from pytest
