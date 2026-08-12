# CI Failure Audit + Required Checks Stabilization v1

Status: **implemented.** This document explains how Required Checks are
structured, how to triage a failed run, and how to classify a failure
honestly. It also records the one confirmed incident this milestone fixed
(PR #203). It does not describe, and should not be read as promising, any
capability beyond what is listed here.

## What "Required Checks" actually gates

`.github/workflows/required-checks.yml` runs two jobs on every PR and every
push to `main`:

- **`core-tests`** -- `pip install -r requirements.txt` against the root
  environment, then `python scripts/run_tests_isolated.py --batch-size 8
  --timeout-s 120`. This installs every dependency declared in root
  `requirements.txt`, including optional/unpinned ones like `fastapi` --
  see [Environment-dependent tests](#environment-dependent-tests) below.
- **`awareness-tests`** -- `pip install -e '.[dev]'` inside
  `apps/awareness_studio/`, then `pytest -q tests`. A fully separate Python
  environment per this repository's documented "Two Python Environments"
  split (see `CLAUDE.md`).

`.github/workflows/ci.yml` (`governance-validate` + `test` matrix across
Python 3.10/3.11/3.12) and `.github/workflows/ontology-claim-language.yml`
run alongside but are **not** the two jobs named `required-checks.yml` --
"Required Checks" in GitHub's branch-protection sense refers specifically to
whichever checks are configured as required on the repository, which as of
this milestone are `core-tests` and `awareness-tests`.

## Environment-dependent tests

Root `requirements.txt` can declare a dependency without every local
development environment actually having it installed -- `fastapi` (line 11)
is the concrete example: unpinned, installed by CI's `pip install -r
requirements.txt`, but absent from this repository's sandbox at the time
`job_runner/api.py` was written (PR #199). **A test must never assert
`some_module.SOME_AVAILABLE_FLAG is <value observed in one environment>`** --
that only stays true in environments identical to the one the test was
written in, and both this sandbox and CI are equally legitimate, equally
"real" environments per this repository's own multi-environment design (see
`CLAUDE.md`'s "Two Python Environments" section).

The correct pattern (established this milestone,
`tests/test_job_runner_api.py`):

1. Assert the availability flag against an **independent probe**
   (`importlib.util.find_spec("fastapi") is not None`), never a hardcoded
   boolean -- this is true in every environment by construction.
2. Test the **unavailable branch deterministically** via `monkeypatch`,
   regardless of what is actually installed, so that branch always has
   coverage.
3. Test the **available branch** only when the dependency is actually
   importable, guarded by `@pytest.mark.skipif(not _ACTUALLY_INSTALLED,
   reason=...)` -- an honest skip, not a silent pass and not a hardcoded
   assumption either way.

## The PR #203 incident (fixed)

- **Failing check:** `core-tests` (Required Checks).
- **Failed batch:** `scripts/run_tests_isolated.py` isolated batch 31/44.
- **Failing test:**
  `tests/test_job_runner_api.py::test_api_unavailable_in_this_environment_is_reported_honestly`.
- **Assertion:** `assert api.API_AVAILABLE is False`.
- **Why it failed in CI but not locally:** root `requirements.txt` declares
  `fastapi` (unpinned). CI's `pip install -r requirements.txt` installs it,
  so `job_runner.api.API_AVAILABLE` is `True` there; the local sandbox this
  test was originally written against does not have `fastapi` installed, so
  it was `False` there. The test hardcoded the local observation as a
  universal fact.
- **Root cause classification:** `environment_dependent` (see
  [Failure classification](#failure-classification) below) -- not a defect
  in `job_runner/api.py` itself, which already handled both branches
  correctly via `try: from fastapi import FastAPI / except Exception:
  FastAPI = None`.
- **Fix:** rewrote the test to probe actual import state instead of
  asserting a hardcoded value, and added explicit, deterministic coverage of
  both the unavailable branch (via monkeypatch, always runs) and the
  available branch (via `skipif`, runs only when `fastapi` is actually
  importable). See `tests/test_job_runner_api.py` and
  [docs/job_runner.md](job_runner.md)'s "Optional local API" section.
- **What was verified:** both branches were exercised locally in this
  sandbox -- once with `fastapi` genuinely absent (the original state) and
  once with it temporarily `pip install`-ed and then removed again to
  restore the original environment -- confirming
  `test_get_app_returns_fastapi_app_when_available` actually executes and
  passes when the dependency is present, rather than being untested dead
  code.

## Failure classification

When a Required Checks (or any CI) run fails, classify the failure before
acting on it. Do not claim a failure is `pre_existing` without evidence
(a `git stash` / prior-commit rerun showing the same failure, or a
documented incident here).

| Classification | Meaning | Evidence required |
|---|---|---|
| `caused_by_current_change` | The failure did not exist before this PR's diff. | Reproduce on `origin/main` or the PR's base commit; if it does not fail there, it is caused by the diff. |
| `pre_existing` | The failure already exists on `main`/the base branch, unrelated to this PR's diff. | Reproduce the same failure on the base commit (locally or by checking a prior CI run), or point to a prior documented incident. |
| `environment_dependent` | The test's assumption differs between two legitimately different environments (local sandbox vs. CI, Python version matrix, optional dependency installed vs. not). | Show the assumption (e.g. a hardcoded flag) and the two real environments where it disagrees. |
| `optional_dependency_branch` | A specific code path only executes when an optional dependency is installed, and that branch is untested/undertested in the environment that lacks it. | Point to the `try/except ImportError`-style guard and confirm the untested branch is the one that failed. |
| `flaky_or_timeout` | The failure is non-deterministic across reruns of the identical commit (timing, network, resource contention). | Rerun the identical commit/job at least once and show a differing result. |
| `out_of_scope_for_required_checks` | The failure is in a workflow/job that is not part of the repository's configured Required Checks (e.g. a full local root `pytest` sweep surfaces failures `required-checks.yml` never runs). | Confirm the failing test file/job is not part of `core-tests` or `awareness-tests` in `required-checks.yml`. |

This table is a discipline, not an automated gate -- nothing in this
repository silently suppresses or reclassifies a CI failure. A human or
agent triaging a failure writes down which category applies and why, the
same way this document records the PR #203 incident above.

## How to inspect a failed GitHub Actions run

1. Identify the failing job name and check conclusion (e.g. `core-tests`,
   `conclusion: failure`).
2. Fetch that job's logs (via the GitHub UI, `gh run view --log-failed`, or
   the GitHub API/MCP `get_job_logs` tool with `failed_only=true`).
3. Find the `[isolated N/M]` line immediately before the failure to identify
   which batch of `scripts/run_tests_isolated.py` failed, and the `FAILED
   ...` pytest lines for the exact node IDs.
4. Reproduce locally: `pytest -q <the failing file(s)>`.
5. Classify per the table above before deciding whether to fix, document as
   pre-existing, or escalate.
6. If the fix changes a test's environment assumption (as in the PR #203
   incident), verify **both** branches locally where feasible -- do not fix
   one branch's assertion while leaving the other branch's code path
   unexecuted by any test.

## Full-root-suite vs. Required Checks

Running the complete local test suite (`pytest tests/ -q`, without
`scripts/run_tests_isolated.py`'s batching/isolation) can surface failures
that Required Checks never runs against -- either because a file is
excluded from `core-tests`' discovery, or because a full monolithic
collection has a different native-library interaction than the isolated
batch runner's fresh-process-per-batch model. A full-root-suite failure is
not automatically a Required Checks problem; classify it
`out_of_scope_for_required_checks` if the failing file/job genuinely is not
part of `required-checks.yml`, with the specific evidence (file path,
workflow file) cited.

## Policy

- Do not claim a failure is `pre_existing` without reproducing it on the
  base commit or citing a documented incident.
- Do not delete or skip a failing test merely to make Required Checks pass.
  A test that encodes a real environment-dependent assumption gets
  rewritten to be portable (see [Environment-dependent
  tests](#environment-dependent-tests)), not silently removed.
- Do not weaken a guardrail scanner to suppress a failure.
- Do not add a dependency to work around an environment mismatch --
  `job_runner/api.py`'s `try/except` fallback pattern is the correct
  response to an optional dependency, not pinning `fastapi` as required.
- This document does not imply Required Checks catches every possible
  regression -- see [Limitations](#limitations).

## Limitations

- This audit process is manual discipline, not an automated failure
  classifier -- `scripts/summarize_ci_failures.py` (if present, see
  `docs/job_runner.md`/this repository's tooling) only extracts failed test
  IDs and batch numbers from a log; it does not classify failures itself.
- The `pre_existing` classification in this document is only as good as the
  evidence cited at the time; a failure classified `pre_existing` today
  could later turn out to be caused by an unrelated change that landed
  between when it was first observed and when it was reclassified.
- Only the PR #203 incident has been fully investigated and documented here
  as of this milestone; other historical CI failures referenced in earlier
  PR reports (job-runner, benchmark-pack, dataset-opportunity milestones)
  were resolved in-session but not retroactively written up in this
  document's incident log.

This document does not imply Required Checks is a scientific-validity gate
-- it verifies code behaves as intended across declared environments, not
that any scientific claim in this repository is correct.
