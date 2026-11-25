# Batch 2 Security Acceptance Harness

Owner:
- `tools/release_readiness/batch2_security/**`
- `scripts/run_batch2_security_audit.py`
- `tests/release_readiness/batch2_security/**`
- `docs/release/batch2_security_acceptance.md`

## What this is

An **additive** engineering security harness for release readiness. It validates
that threat detectors and isolation guards behave correctly against synthetic
fixtures. It does **not** modify production data-access, solvers, Awareness
Studio, or topology code. It does **not** certify scientific validity.

`security_pass` ≠ `scientific_pass`.

## Threat classes covered

| Class | Check |
| --- | --- |
| Network default enabled / opt-in | `network_policy` |
| Full-object / full-dataset / curl / wget / urllib / boto3 / aws sync | `static_scan` |
| Output-root traversal, absolute/drive escapes, symlinks, atomic report replacement | `path_containment` |
| Exact-path allowlist for fixed fixtures, `shell=False`, finite timeout, bounded streaming IO | `subprocess_isolation` |
| Finite JSON (reject NaN/Infinity) | `finite_json` |
| Fabricated provenance, missing checksum/commit, synthetic→empirical | `evidence_boundary` |
| Failed / partial / timed-out / interrupted / malformed or unknown artifacts | `artifact_states` |
| Security vs scientific PASS separation | `security_vs_scientific` |

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Harness acceptance battery passed (`security_pass=true`) |
| `1` | One or more security checks failed |
| `2` | CLI usage error |

## Run

```bash
PYTHONPATH=. python scripts/run_batch2_security_audit.py \
  --output artifacts/batch2_security

PYTHONPATH=. python -m pytest tests/release_readiness/batch2_security -q
python -m compileall tools/release_readiness/batch2_security scripts/run_batch2_security_audit.py
git diff --check
```

## Remediation owners

Findings name exact production owner paths for follow-up. This harness never
edits those files. See `REMEDIATION_OWNERS` in
`tools/release_readiness/batch2_security/schema.py`.

## Tooling status

When `ecc:*`, `gstack:*`, `$coderos-operator`, `$openai-developers:agents`, or
REA are unavailable in the agent environment, the report records
`UNAVAILABLE` / `REA_UNAVAILABLE` and continues with local equivalent checks.

## Limitations

- Fixture detection proves scanner coverage, not repository-wide compliance.
- Report destinations are a trusted local path for the CLI. Callers that need
  containment must pass `trusted_root` to `write_reports`. This is a local
  harness boundary, not a repository-wide security certification.
- Trusted-root checks reject report-file symlink escapes; atomic replacement
  prevents an existing hard link from redirecting report contents to another
  path. These pathname checks are not race-proof against concurrent parent
  directory replacement.
- `no_network()` blocks socket creation in the current Python process; it is
  not an OS firewall or a sandbox for arbitrary subprocess code. An executable
  allowlist does not constrain child-process arguments; the harness only runs
  fixed local print/sleep fixtures.
- POSIX timeout cleanup kills the subprocess group. On Windows, cleanup kills
  the direct child only; spawned descendants are not guaranteed to terminate.
- Worker-limit validation uses the caller-reported `active_workers` value; the
  helper does not manage a process-wide worker pool.
- No network, no neurodata, no credentials, no AWS/DANDI/OpenNeuro access.
- A green security harness is not a scientific PASS.
