# CI installation reliability

## Scope

Ordinary pull-request and main-branch validation uses only
`requirements-base.txt` from PR #213. That profile contains the numerical,
governance, contract, and test-runner dependencies, but no PyTorch, CUDA,
NVIDIA, cloud SDK, QPU SDK, MNE, or research-index packages.

The master `requirements.txt` remains the complete developer/research
environment. It is not installed by ordinary CI because its transitive ML and
research stack can select multi-gigabyte native runtimes.

## Failure classification

The common failures observed on PRs #209–#212 occurred before test execution:
the full requirements install exhausted the GitHub runner disk while resolving
CUDA/NVIDIA packages. The failure is therefore a dependency-environment
failure, not evidence of a scientific regression. Later runs also showed
GitHub Actions account billing/spending-limit failures; those jobs were never
started and must remain infrastructure-blocked rather than being reported as
passes.

## Workflow topology

| Workflow/job | Trigger | Profile | Purpose |
| --- | --- | --- | --- |
| Required Checks / `core-tests` | pull request, `main` push | base | required CPU/core tests in fresh workers |
| Required Checks / `awareness-tests` | pull request, `main` push | app-local | offline Awareness Studio tests |
| CI / governance | pull request and pushes | PyYAML only | governance validation |
| Smoke | pull request, `main` push | base + app-local | synthetic and cross-system offline smoke |
| DS005620 E2E | pull request, `main` push | base | mock-only governance/scientific contract gate |
| Optional Scientific Profiles | manual dispatch | EEG/NWB/research/ML/live/quantum | explicit profile validation |
| Docker build / CPU image | pull request, `main` push | base | CI-only CPU Docker image |
| Docker build / production root image | manual dispatch only | master | intentionally full optional environment |

The CPU/core jobs are the only required scientific execution path. Optional
profile jobs are separate so a missing optional package is visible as a
profile-install or profile-test result, rather than being silently hidden in a
base job. `test_topology.py` is run by the research profile because its
`cripser` gate is not part of the base profile.

GPU, cloud, and QPU jobs are manual inputs. The GPU job requires a configured
self-hosted runner with labels `self-hosted`, `linux`, `x64`, and `gpu`. The
cloud and QPU jobs run contract tests only, with AWS instance metadata disabled
and no credentials or dataset downloads. They do not execute remote jobs.

## Installation controls

Every pip-using job sets `PIP_NO_CACHE_DIR=1` and
`PIP_DISABLE_PIP_VERSION_CHECK=1`, uses `python -m pip`, writes build
temporary files below the job's `${RUNNER_TEMP}/nts-pip-tmp`, and removes that
directory plus any pip cache in an `always()` cleanup step. Install and test
diagnostics record UTC time, filesystem capacity, pip cache information, and
temporary-directory size as an artifact without exposing credentials.

The CPU ML profile preinstalls the pinned CPU-only `torch==2.9.1+cpu` wheel
before installing PR #213's ML profile. The GPU profile is the only workflow
path that may install a GPU-capable ML environment, and it verifies CUDA
availability before running its tests.

## Trigger and failure semantics

Pull requests use `pull_request` triggers so the merge ref is validated;
`main` pushes provide post-merge validation. Concurrency groups cancel stale
runs for the same PR/ref, preventing duplicate dependency installations from
competing for runner disk. Optional profiles intentionally use
`workflow_dispatch` and are never converted to passing skips when their
runner, dependency, or test command fails.

Synthetic and mock executions remain engineering checks only. The scientific
K guardrail is unchanged: K > 100 is the only PASS condition; missing,
insufficient, invalid, or non-empirical inputs cannot become a scientific
PASS.
