# CI resource preflight and failure evidence

`tools.ci_resource_audit` is a read-only, local-only diagnostic package for
separating resource and infrastructure blockers from actual test failures. It
does not contact GitHub, install packages, delete caches, launch Docker builds,
or change workflow configuration.

## Usage

From PowerShell or a POSIX shell:

```text
python scripts/audit_ci_environment.py --format summary
python scripts/audit_ci_environment.py --format json --out ci-resource-audit.json --summary-out ci-resource-audit.txt
python scripts/audit_ci_environment.py --log captured-ci.log --format summary
cat captured-ci.log | python scripts/audit_ci_environment.py --log - --format json
```

Windows PowerShell uses the same command shape:

```powershell
Get-Content .\ci.log -Raw | python scripts/audit_ci_environment.py --log - --format summary
```

Log mode is intentionally offline. It parses only the supplied text and does
not ask GitHub whether a job ran. The JSON contract is described by
`tools/ci_resource_audit/schema.json`.

## Collected facts

When available, the environment report records operating system and
architecture, Python implementation/version, CPU count, repository and
temporary-directory disk capacity, total/available memory, pip cache location
and size, Docker CLI availability/version (without checking or starting a
daemon), installed package versions, optional package availability,
CUDA/NVIDIA package and executable presence, and safe GitHub Actions markers.

Unavailable numerical facts are JSON `null`; the audit never substitutes a
guess. Package discovery uses local import metadata only. The report records
`read_only: true`, `network_accessed: false`, and an empty mutation list.

Use `--timestamp` only when an explicitly variable timestamp is wanted. Without
it, the report does not contain a generated timestamp. Sorted JSON keys and
sorted package maps make the representation stable apart from live resource
values.

## Failure classification

Captured logs are classified using explicit signatures:

- `test_failure`: pytest/test assertion or failure summary evidence.
- `import_failure`: missing-module or import/DLL errors.
- `dependency_resolution_failure`: pip resolver, distribution, or wheel-build
  resolution evidence.
- `disk_exhaustion`: ENOSPC, quota, or no-space evidence.
- `memory_exhaustion`: `MemoryError`, OOM, allocation, or explicit OOM exit
  evidence.
- `network_resolution_failure`: DNS, connection, proxy, or network failure
  evidence.
- `billing_or_runner_blocked`: explicit billing, payment, spending-limit,
  Actions quota, disabled-account, or runner-blocked evidence.
- `workflow_configuration_failure`: invalid workflow, YAML, permission, or
  Actions configuration evidence.
- `unknown_infrastructure_failure`: explicit runner failure or an otherwise
  unclassified timeout/failure.

Generic `timeout` text is never converted into a billing classification. A
billing result requires an explicit billing/account/quota signature. A billing
log with no start marker reports `job_never_started: true`,
`tests_passed: false`, and `pass_status: not_evaluated`; no test is reported as
passing when the job never began.

Empty logs are valid input with no detected failure. Non-text input is invalid
and returns `unknown_infrastructure_failure` without raising. The classifier is
deterministic and returns matched signatures so a merger agent can audit why a
classification was made.

## Interpretation boundary

These diagnostics explain execution evidence; they do not prove that a test
would pass on another runner. Disk exhaustion, memory exhaustion, dependency
resolution, and billing/runner blocks must be reported separately from test
failures. In particular, GitHub billing restrictions are external evidence and
cannot be inferred from a local timeout alone.
