# Signal interoperability contract

This document defines the narrow boundary between signal adapters and
NeuroTopology-Sim analysis. It is metadata-first and offline-safe. It does not
replace the canonical `runs.run_record.RunRecordV1`, governance specifications,
or any scientific analysis module.

## SignalChunk

`SignalChunk.data` is a numeric array with exactly two dimensions:

```text
(channels, samples)
```

`SignalChunk.timestamps` is a one-dimensional numeric array with shape
`(samples,)`. Timestamps must be finite and strictly increasing; duplicate
timestamps are invalid. `sample_rate_hz` must be finite and greater than zero.
The contract never transposes an input array. A shape mismatch is an explicit
validation error.

`channel_names` and `units` each have one entry per channel. A single unit
string may be used as a documented shorthand for all channels. Channel names
must be non-empty and unique, except when `allow_duplicate_channels=True` is
set explicitly by the caller. This exception is for adapter interoperability,
not permission to ignore ambiguous channel identity.

Optional `montage_coordinates` has exactly shape `(channels, 3)` and represents
finite coordinates in the montage's declared coordinate system. Coordinates
are not inferred, projected, or silently transposed. `montage_name` identifies
the coordinate convention when one is known.

Chunk identity and alignment fields are `source_id`, `recording_id`,
`chunk_index`, and `start_sample`. `chunk_index`, `start_sample`, and
`dropped_samples` are non-negative integers. `source_sha256`, when supplied,
must be a 64-character SHA-256 digest. Warnings are retained as explicit
strings.

## RecordingManifest

`RecordingManifest` describes one recording without embedding raw samples. It
contains the dataset and recording identifiers, a canonical relative
`source_path`, source hash, file format, channel/sample-rate/duration metadata,
channel names, units, montage metadata, preprocessing history, data mode,
provenance status, software versions, warnings, and errors.

Source paths and quality artifact paths are normalized to POSIX separators and
must be relative. Absolute paths, drive-qualified paths, UNC paths, and `..`
traversal are rejected. This keeps serialized artifacts portable and avoids
leaking machine-local layout. A missing source hash is represented explicitly
as `None`; it is not silently replaced with a fabricated digest.

Recommended `data_mode` values are `real`, `synthetic`, `external`, and
`unknown`. Recommended provenance statuses are `verified`, `partial`,
`synthetic`, `missing`, and `invalid`. These values describe provenance; they
do not constitute scientific evidence.

## Metadata and binary arrays

Canonical JSON uses sorted keys, UTF-8, compact separators, and rejects
non-finite values. NumPy scalar values are converted to JSON scalars. NumPy
arrays are intentionally rejected by the generic JSON converter: they belong
in a separately managed binary artifact. `SignalChunk.to_metadata_dict()` and
`serialize_signal_chunk()` emit shape, timestamps, and metadata plus an
optional caller-supplied `array_reference` (for example, a relative path,
format, shape, dtype, and binary SHA-256). They do not embed `data` unless a
caller explicitly requests the non-canonical `to_dict(include_data=True)`
view for a local test or debugging operation.

Stable hashes are SHA-256 over canonical JSON. Stable IDs are deterministic
prefix-plus-digest prefixes and exclude volatile timestamps and raw binary
payloads unless the caller includes a binary reference in the hashed value.

## Adapter capabilities

`AdapterRegistry` declares the supported native interop surface for NumPy,
SciPy, MNE, MNE-BIDS, NWB, LSL, BrainFlow, Semantica, Scrapling, PyTorch,
Braindecode, and snnTorch. It checks availability lazily with
`importlib.util.find_spec`; it never imports those packages at module import
time, opens a socket, downloads data, or initializes a solver.

Capability status is one of:

- `integrated`: a repository adapter can use the dependency when installed;
- `emulate`: the boundary is represented for local/offline emulation;
- `reference`: the dependency is recorded as an intended/reference backend;
- `unavailable`: the dependency is not installed in the current environment.

Availability is separate from capability status. An unavailable dependency is
always reported as `unavailable`, never as an inferred scientific failure.
Network requirements are descriptive metadata. Tests must remain network-free;
real acquisition is an explicit operator action outside this contract.

## QualityReport and status semantics

`QualityReport.status` is explicitly one of `PASS`, `FAIL`, `INCONCLUSIVE`, or
`ERROR`. Checks, errors, warnings, metrics, provenance, and relative artifact
paths are carried separately. Missing, malformed, non-finite, or insufficient
inputs must remain `INCONCLUSIVE`, `FAIL`, or `ERROR` as appropriate; they must
not be turned into a pass by a default or a synthetic fallback.

The repository-wide scientific guardrail remains unchanged: a scientific
claim may use `PASS` only when its K criterion is satisfied with `K > 100`.
When a `QualityReport` carries a `K` metric, it rejects `PASS` for non-finite
or `K <= 100`. A generic adapter-quality report without K evidence does not
invent a K result. Metadata alone is never empirical evidence, and synthetic
signals are test fixtures only.

The contract does not conflate graph beta_1, spatial winding, spatial charge,
or scalar chirality. If a downstream analysis reports any of these, it must
use distinct metric names and provenance.

## RunRecordV1 and governance relationship

`RunRecordV1` in `runs/run_record.py` remains the canonical run artifact. The
`QualityReport.from_run_record()` helper is a thin read-only compatibility
mapping: it copies the existing verdict, metrics, artifact paths, and selected
provenance into a quality view. It does not write or define a replacement run
record schema. Awareness Studio can continue consuming the existing
`metrics` and `artifacts` fields and exporting RunRecord JSON to Markdown.

Governance remains owned by `governance/spec.py` and
`governance/validate.py`. The interop contracts carry governance identifiers
and provenance; they do not reinterpret hypothesis claim types or weaken
governance gates. CoderOS-style `RunSpec`/`QualityReport` integrations should
map into these fields only when such an external type is present, with no
second orchestration framework.

## Units and scientific boundaries

Sample rates are expressed in hertz, durations in seconds, timestamps in
seconds relative to the recording/chunk time origin, and montage coordinates
in the coordinate system named by `montage_name`. Channel signal units are
explicit strings such as `uV` and are not guessed from values.

Raw signal data, derived metrics, and provenance are separate layers. A
derived topology or feature metric must retain its source recording/chunk
identity, preprocessing history, software versions, and quality status.
Incomplete or invalid data must be surfaced rather than repaired implicitly.
