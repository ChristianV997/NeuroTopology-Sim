# Legacy streaming migration

This change migrates the non-OpenNeuro NKI-RS and HCP-YA readers, plus the
`ds005917` and `ds006644` streaming scripts, away from direct S3 full-object
transfers. It does not download data and does not make a scientific claim.

## Access contract

`validation.s3_fetchers.BoundedS3ObjectStore` is the owned boundary:

1. Network access is disabled unless the caller passes `allow_network=True`.
   Omitting the permission is equivalent to `False` for real clients.
2. A `head_object` metadata response must provide an integer object size.
   Missing or conflicting sizes are rejected.
3. Every data request uses an explicit `Range` whose width is bounded by
   `chunk_size`; boto3 full-object transfer helpers are not used.
4. The source URI, object size, checksum (or explicit unknown state), chunk
   size, and status are persisted in `.bounded_s3_manifest.json`.
5. Data is written to `<destination>.part` and progress to
   `<destination>.part.json`. Only a complete, size-consistent, checksum-valid
   transfer is atomically renamed to the destination.
6. Transient failures receive a bounded retry count and bounded backoff.
   Non-transient failures stop immediately and preserve resumable progress.
7. A declared SHA-256 is verified. If the source supplies no usable checksum,
   the record remains `checksum_status=unknown`; no checksum is fabricated.
8. Managed completed files are evicted in deterministic least-recent-access
   order when the explicit cache budget requires space. Unmanaged files are
   never silently deleted.
9. A final consumer releases an object through its exact S3 URI and contained
   destination identity. The bytes and partial state are removed, while the
   manifest retains a `released` tombstone with the release reason and size.
   Released or externally deleted objects cannot be reused offline.

The streaming scripts expose `--allow-network` and `--max-cache-bytes`. Their
default invocation fails closed before metadata or data access. Each temporary
BOLD object is identity-released immediately after its final subject/session
consumer, before the next unit begins. Failed transfers remain represented by
their partial state rather than being presented as valid artifacts.

## Metadata and provenance

`participants.tsv` is read through the same bounded path with a 4 MiB metadata
limit. Subject conditions are taken from that real metadata, not inferred from
names. `validation.fast_tr_fixtures` remains a plan-only compatibility API and
returns `PLAN_ONLY_BOUNDED_ADAPTER_REQUIRED`; its output is not evidence that a
dataset was fetched.

The cache manifest records the S3 object identity and expected size. A missing
source checksum is intentionally unknown. Local fixtures and mocked S3 objects
are test infrastructure and must not be labeled as empirical data.

## Migration inventory

Before migration, the owned production paths contained direct
`download_file` calls and unbounded `get_object(...)["Body"].read()` metadata
reads. After migration, those direct full-object and unbounded reads are gone.
The integrated policy registration recognizes the exact bounded store and
delegating symbols only after structural checks for range access, explicit
network permission, checksum state, atomic staging, containment, cache bounds,
and observable eviction. The owned-path policy audit reports zero findings.
`validation.s3_fetchers.POLICY_REGISTRATION_REQUIREMENTS` remains the
machine-readable registration contract; it is not a filename-wide bypass.

The only compatibility seam is for `unittest.mock` clients used by existing
parser fixtures. It issues a bounded metadata probe and cannot access AWS;
real boto clients still fail closed when permission is omitted. The probe is
never labeled checksum-verified empirical data.

## Scientific limitation

Bounded transfer, checksums, resumability, and provenance records establish
engineering integrity only. They do not establish a biological effect,
causality, consciousness, or any other scientific conclusion.
