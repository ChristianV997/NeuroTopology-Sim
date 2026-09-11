# Bounded data-access policy

This policy is an engineering control. A clean audit does not constitute
scientific evidence, biological validation, or a claim about a dataset.

## Required access lifecycle

1. Build or validate a manifest before requesting data bytes.
2. Use an approved acquisition adapter and an explicit output/cache root.
3. Require a known object size, or reject unless an explicit operator override
   is recorded. Unknown size is never silently treated as safe.
4. Transfer only a bounded byte range or another explicitly bounded unit.
5. Stage partial transfers separately. A partial object is never marked
   complete.
6. Verify a source checksum when provided. If no checksum is provided, retain
   `null`/unknown; never fabricate one.
7. Retry only a bounded number of times and record failures.
8. Resume only verified manifest entries.
9. Keep cache occupancy within a declared budget. Eviction must be observable
   and cannot remove an active lease silently.
10. Record that network access was opt-in and visible in the resulting
    manifest.

The default policy is network-disabled. The scanner itself is read-only and
does not import or execute production download code.

## Access classes

| Class | Allowed behavior |
| --- | --- |
| Metadata inventory | Object listings, headers, manifests, or GraphQL metadata; no object body transfer. |
| Bounded byte-range transfer | Explicit range, known size, partial staging, checksum/lifecycle metadata, and approved adapter. |
| Lazy remote reading | Explicit reader with bounded reads and visible network opt-in; not full materialization. |
| Full-dataset download | Rejected by this policy. A single full-object transfer is not automatically a bounded dataset operation. |

Approved adapters and metadata operations are declared in
`tools/data_access/policy_enforcement/policy.py`. The allowlist is intentionally
narrow. Reviewed exceptions must name an exact path, rule, reviewer, and
justification; a comment or a 40-character hash is not an exception.

## Rejected patterns

The static scanner reports exact file and line for direct `openneuro download`,
`aws s3 cp`, `aws s3 sync`, `wget`, `curl`, direct boto3 full-object methods,
unapproved `urllib`/`requests` retrieval, unbounded `get_object`/response reads,
and other unbounded remote materialization. Each report includes severity and
remediation. A parse failure is critical and fails closed.

Run an audit without network access:

```text
python scripts/validate_data_access_policy.py --output policy-audit.json
```

The JSON contains the allowlists, runtime policy, exact findings, and a
deterministic migration inventory of legacy callers. A non-empty finding set
means repository-wide compliance has not been established. Legacy callers are
reported, not silently converted to compliant.

## Current migration posture

The existing chunk-cache package is the intended bounded-access boundary. The
repository still contains legacy direct readers and transfer paths, including
streaming/base-runner and older OpenNeuro scripts. This task does not modify
those callers. The audit must therefore remain blocked until each finding is
reviewed and migrated or receives a recorded exception.

## Containment

Output and cache roots must be explicit children of their configured roots.
Both POSIX and Windows path styles are checked lexically by the policy helper;
runtime file-openers should additionally resolve symlinks before opening a
path. Equal-root writes and cross-drive/escaping paths are rejected.

## Scientific limitation

Manifest integrity, checksums, bounded transfer, and policy compliance are
engineering evidence only. They do not establish data validity, a biological
effect, causation, or any scientific conclusion.
