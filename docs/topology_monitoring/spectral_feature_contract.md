# Spectral feature contract adapter

The adapter converts a JSON-compatible higher-order spectral report into
canonical comparison records without changing the estimator or shared feature
contracts. It is an additive boundary for comparing PSD, PAC, pairwise
cross-frequency features, bispectrum, selected trispectrum slices, and
modulogram features.

The adapter does not download data, call a signal loader, contact a network,
or infer topology, graph beta-1, spatial charge, causal direction,
consciousness, or mental-state labels.
## Schema

The canonical schema is:

`NeuroTopologySim.SpectralFeatureContract.v1`

Each `CanonicalFrequencyRecord` preserves:

- feature family and value shape;
- frequency axes, units, and declared resolution;
- sampling rate, FFT length, segment length, overlap, taper, and memory budget;
- channel identity and condition label;
- surrogate method, seed, count, and block length;
- source checksum and synthetic/empirical status;
- filtering declaration and explicit edge-effect metadata;
- finite values, complex values represented as `{real, imag}`, warnings, and
  validation errors.

The contract evidence class is descriptive signal processing:

- `empirical_signal_processing_descriptive`;
- `synthetic_signal_processing_descriptive`;
- `unknown_signal_mode` when provenance is incomplete.

Synthetic status is never converted into empirical evidence.

## Validation rules

The adapter rejects or records errors for missing/invalid sampling rate,
non-monotonic frequency axes, nonfinite values, incompatible matrix shapes,
missing checksums, malformed complex values, and negative PSD-like quantities.
Missing filtering metadata is reported as `not_declared`; it is never silently
treated as “no filtering.” Missing edge-effect metadata is an explicit warning.

Unavailable comparison families remain absent from `records` rather than being
fabricated. A valid cross-spectrum preserves magnitude and phase separately.
The adapter also preserves selected trispectrum slice frequencies as a
separate axis and never labels them topological.

## CLI

Validate and render a local report without network access:

```text
python scripts/validate_spectral_feature_contract.py \
  --input higher_order_report.json \
  --output-json canonical_contract.json \
  --output-markdown canonical_contract.md \
  --channel-identity left-right \
  --condition-label amplitude-modulated-carrier
```

JSON and Markdown output are deterministic. JSON serialization rejects
`NaN`/`Infinity`, and invalid CLI input produces a finite error envelope.
