# CI test execution and root-cause record

## Common PR failure

The common failures on PRs #210, #211, and #212 were reproduced from their
GitHub Actions runs. `awareness-tests` passed. The failing jobs were:

- `core-tests` in Required Checks;
- `ontology-claim-language`;
- `Cross-system smoke`.

All three stopped at dependency installation before their test/validator
commands ran. The logs end with `OSError: [Errno 28] No space left on device`
while installing the unbounded root `requirements.txt` environment. The
dependency set pulled CUDA-enabled PyTorch/NVIDIA wheels in addition to the
repository's optional research stack. This is a baseline CI environment
failure common to all three PRs, not a regression in any PR's changed files.

## Dependency profiles

The ontology-language job runs only `tools/validate_ontology_claim_language.py`
and therefore installs only its declared parser dependency, `pyyaml`. The
root test, smoke, and DS005620 mock jobs preserve the full declared
`requirements.txt` install, but first install the pinned CPU-only
matching CPU-only `torch==2.9.1+cpu` and `torchaudio==2.9.1+cpu` wheels and
disable pip caching. This avoids pulling the
multi-gigabyte CUDA runtime while retaining the PyTorch API required by tests.
Optional packages remain explicit: tests that declare an optional dependency
use the repository's existing skip policy, while the isolated runner fails
clearly if the required `pytest-timeout` plugin is missing.

## Isolated runner contract

`scripts/run_tests_isolated.py` discovers files in sorted path order, separates
known MNE/SciPy/Matplotlib/GUDHI/Torch and dense-matrix tests into singleton
workers, limits each worker with pytest's per-test timeout plus a 30-second
process grace period, and terminates the complete process group on timeout.
It continues to later batches after a failure or timeout and returns non-zero
after all attempted batches, so failures are never hidden.

Each run writes `test-results/isolated/batch_summary.json` and one stdout and
stderr log per batch. Each summary item contains `batch_number`, `test_files`,
`duration_s`, `exit_code`, `timed_out`, `timeout_status`, `stdout_path`, and
`stderr_path`. JSON paths use POSIX separators for portable CI artifact use;
worker commands and process-group handling remain native to Windows or POSIX.

The runner sets `MPLBACKEND=Agg`, bounds BLAS/OpenMP pools to one thread, and
uses fresh interpreters. It does not access the network or download datasets.
The root pytest configuration requires `pytest-timeout`, sets a 120-second
default, and the root `conftest.py` restores Python/NumPy/Torch RNG state and
closes leaked Matplotlib figures after each test. These are test-process
controls only; scientific model semantics and assertions are unchanged.

## Validation interpretation

The CI fix does not assert that a scientific model passes. Synthetic smoke
paths remain synthetic checks only. The repository's K guardrail is unchanged:
K > 100 is required for a scientific PASS; missing, invalid, or insufficient
inputs remain failures or inconclusive outcomes.
