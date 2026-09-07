# Release-candidate CI stabilization

This document defines the bounded CI contract for a release candidate. It is
an execution and provenance contract; a green job is not scientific evidence,
biological confirmation, or a Bayesian PASS.

## Evidence basis

PRs #249 and #257 reproduced two local defects from the integration workflow:

- CI referenced a dependency named `fast-contracts` in configurations where the
  job was absent or inconsistent with the workflow graph.
- The shared eight-file core worker exceeded its 120-second bound, while the
  same files passed when each file received a fresh isolated process.

The associated remote failures did not provide job steps or downloadable logs;
GitHub returned `BlobNotFound`. They therefore remain unavailable
runner/log-infrastructure evidence, not test failures, billing proof, or green
checks.

## Stable checks

The release contract validates exactly one automatic definition for each of:

- `core-tests`
- `awareness-tests`
- `ontology-claim-language`
- `Cross-system smoke`
- `DS005620 E2E Mock Run`

The validator also rejects undefined `needs` references, invalid YAML-level
job/step shapes, contradictory required-check placement, and missing positive
job timeouts.

## Dependency and isolation policy

Automatic CPU/core jobs install only `requirements-base.txt` with pip cache
writes disabled. The aggregate `requirements.txt` and optional ML, EEG, TDA,
GPU, cloud, and QPU profiles are not installed by automatic CPU checks. ML and
EEG jobs in `ci.yml` are manual-dispatch only. Missing optional packages such
as `torch`, `cripser`, MNE, or GPU runtimes remain explicit unavailable or
`NOT_SUPPORTED` states; they are never converted into a passing capability.

The core release path uses singleton `run_tests_isolated.py` batches. This
preserves real test assertions while limiting native allocation retention and
preventing one unstable group from blocking the complete core check.

The automatic Docker root job uses `docker/ci/core.Dockerfile`. The aggregate
production `Dockerfile` is available only through an explicit manual
`run_full_root` dispatch input.

## Diagnostics

`scripts/validate_release_ci_contract.py` emits deterministic JSON using
`release-ci-diagnostic-v1` with these fields:

`workflow`, `job`, `step`, `exit_code`, `timeout_state`, `dependency_state`,
`failure_classification`, `resource_classification`, `artifact_path`,
`actionable`, and `infrastructure_blocked`.

The classifier distinguishes test, import, dependency-resolution, disk,
memory, network, billing/runner, workflow-configuration, timeout, and unknown
infrastructure failures. JSON is written with `allow_nan=False`; non-finite
values are rejected.

Every automatic test-like job has an unconditional artifact upload for its
report or diagnostic. A failed step remains a failed job. Optional capability
absence is reported explicitly rather than silently skipped.

## Validation boundary

The local release checks validate workflow structure, deterministic JSON,
governance files, Python compilation, and no-network workflow intent. GitHub
Actions, Docker, billing, runner capacity, and log retention are external
systems. If they do not execute with usable steps and logs, the release state
is infrastructure-blocked and must not be represented as green.
