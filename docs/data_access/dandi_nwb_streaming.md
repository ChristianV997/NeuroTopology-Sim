# Bounded DANDI/NWB streaming

`data.dandi_nwb_ingest` separates metadata inspection from signal retrieval.
Metadata readers receive only dataset/object identities. DANDI asset resolution
requires `network_permission=True` and reads only a bounded manifest prefix;
remote NWB opening also requires that explicit permission. Signal readers
require an explicit `WindowRequest` with a half-open byte or sample range,
expected returned size, checksum policy, cache budget, consumer lease,
eviction policy, and an explicit network decision.

The default contract is fail-closed:

- full-recording materialization is rejected;
- unknown source size and oversized windows are refused;
- offline mode cannot grant network permission;
- incomplete provenance and filesystem fallbacks are blocked;
- short, interrupted, invalid, or checksum-mismatched reads are not complete;
- a checksum is emitted only for a complete validated window;
- cached bytes are bounded to windows, protected by active leases, and released
  after the final consumer.

The DANDI 000458 CLI is opt-in (`--allow-network`), resumes at the asset
manifest boundary, records the published asset SHA-256 when present, writes
only under its explicit `--output-root`, and closes each NWB handle after the
final window. The source checksum identifies the published object; lazy
window reads do not download the whole object to re-hash it. Output CSV
checksums and per-window fixture/read checksums are recorded separately.

The local file source is for hermetic engineering fixtures only and is labeled
`engineering_fixture_only`; it is not validated DANDI/NWB provenance. No test
contacts DANDI, AWS, or any other live dataset service.

Example request:

```python
request = WindowRequest(
    provenance=Provenance(
        dataset_identity="DANDI:000458/0.240318.0000",
        object_identity="sub-521885/session.nwb",
        source_kind="dandi_nwb",
        source_uri="https://approved-reader/object",
        validated_dandi_nwb=True,
    ),
    start=0,
    stop=4096,
    unit="bytes",
    expected_size=4096,
    checksum_policy="sha256",
    expected_checksum=None,
    cache_budget_bytes=1 << 20,
    consumer_lease="forecast-run-1",
    eviction_policy="release_after_final_consumer",
    network_permission=True,
)
result = read_bounded_window(source, request, cache=WindowCache(1 << 20))
```

`result.to_dict()` is finite JSON-safe metadata and deliberately excludes
signal bytes. `PARTIAL`, `FAILED`, `BLOCKED`, and `OFFLINE_BLOCKED` states are
engineering/readiness outcomes, not scientific evidence or causal claims.
