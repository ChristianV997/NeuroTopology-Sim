# Integration CI failure repair

The live PR #236 head was `be277ecdac301d49dca27ef9612ebe6c560245ad`.
The associated workflow runs completed with failures in core, Awareness,
ontology-language, DS005620 E2E, Docker, and cross-system smoke checks.

## Evidence classification

The GitHub Actions job listing reported all of those jobs as completed with
failure, but the job-step API returned no steps and every log download returned
`BlobNotFound`. The available evidence therefore does not distinguish a test
assertion from an installation or runner failure for those jobs. They are
classified as **unknown until reproduced**, not as passing and not as billing
failures.

One deterministic configuration defect was reproducible locally: `.github/workflows/ci.yml`
declared `needs: fast-contracts` for three jobs, but no `fast-contracts` job
exists. The repair points those jobs at the existing governance and dependency
inventory jobs.

The automatic CPU paths use `requirements-base.txt`; the automatic CI workflow
no longer installs the optional ML profile. The ML CPU/GPU, EEG, NWB, research,
cloud-contract, and QPU-contract paths remain in the explicit manual
`optional-scientific.yml` workflow. Production-root Docker builds remain manual
opt-in.

All pip jobs disable cache writes, use a bounded runner temporary directory,
capture disk/install diagnostics on failure, and clean temporary files in an
unconditional step. These controls expose the first installation failure
without turning optional dependency failures into skips.

The required CPU/core workflow and its CI Docker image use singleton isolated
batches. The individual core files pass independently, while the combined
eight-file worker timed out locally; singleton workers prevent that shared
process interaction from blocking the entire core check.
