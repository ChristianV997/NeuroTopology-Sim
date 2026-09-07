# Triadic functional connectivity

This feature layer computes bounded statistical dependence features for channel
triplets. It is an engineering implementation of a promising matrix-entropy
and higher-order-dependence methodology, not an established causal-neuroscience
method. Synthetic demonstrations are validation fixtures only.

## Input contract

`SignalWindow` accepts a finite NumPy array with shape
`(channels, samples)`. The orientation is strict: arrays are never silently
transposed. It can also represent a precomputed feature matrix by setting
`input_kind="feature_matrix"` or by passing `feature_matrix=` to
`estimate_triadic_connectivity`.

Optional channel labels must be unique and have length `channels`. Optional
condition labels have length `samples`; they are retained in the result as a
deterministic condition-count summary. Optional timestamps have shape
`(samples,)`, are finite, and must be strictly increasing. A positive sampling
rate is accepted when known. NaN and Infinity are rejected.

## Schema and estimators

The result schema version is `triadic-functional-connectivity-v1`. It contains:

- bounded `interactions` and deterministic `top_triads`;
- `TriadicEntropySummary` records for
  `matrix_entropy_covariance` and
  `residualized_three_variable_dependence`;
- pairwise-connectivity and PSD controls;
- descriptive community and strength-ranking summaries;
- optional amplitude-shuffle, phase-shuffle, circular-shift, and block-shift
  surrogate comparisons;
- effective channel count, condition counts, finite-value status, and
  optional-dependency status;
- source and parameter checksums plus a deterministic provenance checksum;
- a `synthetic_demo` marker.

The covariance estimator normalizes a three-channel correlation matrix to a
density matrix and reports normalized entropy deficit relative to independent
channels. The nonlinear estimator residualizes each variable against the other
two using an intercept-inclusive linear model and measures the normalized
third-order residual product. The nonlinear feature is useful for a synthetic
`z = x*y` interaction even when pairwise correlations are small; it is not a
causal interaction estimate.

## Bounded complexity

`max_channels` limits the channel set and `max_triads` limits candidate
triplets. If the selected channel count has no more than `max_triads`
combinations, enumeration is exhaustive within that bound. Otherwise a
deterministic sparse stencil is used without materializing all `O(N^3)`
combinations. The result exposes:

- input and effective channel counts;
- candidate and theoretical triplet counts;
- enumeration mode;
- estimated input and candidate memory;
- an explicit `bounded: true` telemetry flag.

`max_memory_mb` rejects an oversized input before estimation. Surrogates are
generated one at a time with deterministic seeds, so they do not accumulate a
second collection of all surrogate arrays.

## Controls and serialization

The pairwise and PSD controls are descriptive checks, not replacements for the
triadic estimators. Surrogate p-values use the finite-sample plus-one rule and
are reported as null comparisons, not formal evidence by themselves.

`to_json()` uses canonical sorted-key JSON, converts unavailable values to
`null`, rejects non-finite JSON numbers, and includes a stable SHA-256 checksum.
No network, dataset download, MNE, SciPy, GPU, or other optional dependency is
required by the estimator. The result records optional dependencies as
`not_required` rather than implying that an unavailable package was tested.

## Namespace separation and limitations

Triadic functional connectivity remains separate from graph beta-1,
spatial phase winding or charge, scalar chirality, and directed causal
influence. A high triadic score does not establish causation, consciousness,
mechanism, quantum coherence, or biological significance. Common-driver
signals can produce strong covariance entropy scores; pairwise controls,
residualized scores, and surrogates must therefore be interpreted together.
Real empirical claims require separately governed provenance, null controls,
sample adequacy, and domain-appropriate validation. Synthetic data never
produces empirical evidence.
