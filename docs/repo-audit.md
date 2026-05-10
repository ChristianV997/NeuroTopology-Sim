# Repository Audit (Current State)

## Scope snapshot

- CLI entrypoint in `main.py` supports eight modes (`synthetic`, `qzt`, `eeg`, `physionet`, `physics`, `cross-domain`, `external`, `db`).
- Pipelines are separated by modality under `pipelines/`.
- Validation/math utilities live in `validation/` and `core/`.
- Awareness Studio is a nested app under `apps/awareness_studio/` with its own tests and packaging.

## Strengths

- Clear mode dispatch and lightweight CLI.
- Existing CI workflows for core, smoke, and Awareness Studio lanes.
- Broad unit test coverage across validation and pipelines.

## Gaps addressed by this audit follow-up

- Missing standalone docs for validation entrypoints and mode contracts.
- Missing contributor setup matrix in root docs.
- Missing root task runner (`Makefile`) for common checks.
- Missing explicit fixtures directory README and root smoke test module.
