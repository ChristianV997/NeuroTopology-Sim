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

## PR #346 registration boundary

The bounded S3 migration in PR #346 is registered by exact production-relative
path and complete enclosing symbol. The registration is declarative and does
not make the current legacy implementation compliant while that migration is
unmerged:

| Path | Qualified symbols | Control profile |
| --- | --- | --- |
| `validation/s3_fetchers.py` | `BoundedS3ObjectStore.fetch_object`, `BoundedS3ObjectStore.read_text_metadata` | manifest-first S3 store |
| `tools/stream_process_ds005917.py` | `download_bold`, `load_mdd_complete_subjects` | delegated bounded S3 wrapper |
| `tools/stream_process_ds006644.py` | `download_subject_bold`, `load_group_labels` | delegated bounded S3 wrapper |

For the S3 store, structural validation requires an explicit
`allow_network=False` default, `head_object`/`ContentLength` object sizing,
`Range` on every data `get_object`, checksum state that can remain explicitly
unknown, atomic partial staging, a cache budget, observable eviction, and
output-root containment. Delegated wrappers must expose the same network
opt-in plus explicit cache and chunk bounds and must call the registered
`BoundedS3ObjectStore` methods. A missing control emits a finding even when
the name resembles an approved adapter.

Qualified matching matters: `OtherStore.fetch_object` and an unrelated
function in `validation/s3_fetchers.py` are not approved by a registration for
`BoundedS3ObjectStore.fetch_object`. Direct HTTP imports are not a path-level
exemption; the retrieval call is checked in its own enclosing symbol. This
prevents an approved comment, basename collision, or filename-only suppression
from hiding a full-object transfer.

## Rejected patterns

The static scanner reports exact file and line for direct `openneuro download`,
`aws s3 cp`, `aws s3 sync`, `wget`, `curl`, direct boto3 full-object methods,
unapproved `urllib`/`requests` retrieval, unbounded `get_object`/response reads,
and other unbounded remote materialization. Each report includes severity and
remediation. A parse failure is critical and fails closed.

The scanner also reports missing controls on unapproved transfer functions:
`MISSING_CACHE_BOUND`, `MISSING_CHECKSUM`, and `MISSING_EVICTION`. It reports
`OUTPUT_ROOT_ESCAPE` for literal parent traversal and
`NETWORK_ENABLED_BY_DEFAULT` for network/download switches whose default is
enabled. These are static indicators; a clean scan does not replace runtime
path containment, checksum verification, or manifest review.

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

The PR #346 caller and S3 implementation paths are likewise outside this
policy-only change. On a checkout where those callers are still legacy, the
repository-wide audit must report their findings. A clean policy-module audit
or a registration declaration is not evidence that an unmerged caller has
been migrated.

The DANDI NWB reader is an explicit exception to the generic remote-reader
rules: `resolve_asset_blobs` is metadata-only for the published assets
manifest, while `open_nwb_lazy` and `read_nwb_eeg_window` are bounded lazy
readers. Their allowlist entry records the required range-read, window, and
provenance conditions; it does not authorize full-object download.

## Containment

Output and cache roots must be explicit children of their configured roots.
Both POSIX and Windows path styles are checked lexically by the policy helper;
runtime file-openers should additionally resolve symlinks before opening a
path. Equal-root writes and cross-drive/escaping paths are rejected.

## Scientific limitation

Manifest integrity, checksums, bounded transfer, and policy compliance are
engineering evidence only. They do not establish data validity, a biological
effect, causation, or any scientific conclusion.
