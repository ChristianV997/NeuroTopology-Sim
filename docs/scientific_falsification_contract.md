# Scientific falsification contract

This contract separates computational diagnostics from empirical claims. A
result can be numerically reproducible without being interpretable evidence.

## Verdicts

| Verdict | Meaning |
| --- | --- |
| `PASS` | Valid empirical data, complete provenance, interpretable analysis, passing declared controls, and a declared formal comparison with `K > 100`. |
| `NOT_SUPPORTED` | Valid and interpretable data do not support the hypothesis at the declared threshold. This also covers synthetic results and RSS/AICc proxies that cannot support an empirical PASS. |
| `INCONCLUSIVE` | Missing or malformed data, constant or degenerate features, insufficient paired subjects, incomplete provenance, failed identifiability, missing controls, or an unsupported model comparison. |
| `ERROR` | Execution or contract failure, such as an invalid method invocation or an exception during computation. |

`K > 100` is the only condition that can produce `PASS`. `K == 100` and
`K < 100` are `NOT_SUPPORTED` when all other requirements are met.

## Formal and proxy Bayes factors

`bayes_factor_from_marginal_likelihoods` accepts marginal likelihoods from an
implemented model, records the model priors and assumptions, and reports the
formal ratio:

\[
K = p(D \mid M_1) / p(D \mid M_0)
\]

`bayes_factor_proxy_from_rss` is different. It reports an exponential of the
negative half AICc difference under a common Gaussian residual convention,
including explicit parameter counts. It is useful for model screening, but it
does not integrate parameters or priors and must never be described as a
formal Bayes factor. `compare_models` retains the legacy `bayes_factor` key
as an alias for the proxy's `k_value`, while `method` identifies the proxy.

## Provenance and uncertainty

An empirical comparison requires a declared data mode, dataset identifier,
source reference, and positive sample rate. The structured result records
`provenance_status`, `sample_count`, `feature_count`, `uncertainty`, `controls`,
`warnings`, and `errors`. Missing provenance is `INCONCLUSIVE`, not evidence
of a null result. Proxy uncertainty is explicitly unavailable unless a caller
supplies a separate uncertainty analysis.

Synthetic fixtures and analytic vortex fixtures are method-validation tools.
They may establish that an implementation recovers a known constructed
answer, but they are not empirical data and cannot produce empirical `PASS`.

## Topology separation

The following fields are intentionally distinct:

- `graph_beta1`: H1 persistence of a similarity graph;
- `spatial_winding_q`: phase winding computed on real coordinates;
- `spin_chain_winding`: winding along an explicitly declared spin-chain order;
- `scalar_chirality`: a separate oriented triple-product observable;
- `defect_density`: density of detected defects; and
- `persistence_landscape_area`: an integrated persistence-landscape summary.

Graph cycle counts are never spatial topological charge. Spatial winding
requires real coordinates, an explicit coordinate frame, an interpolation
method, and (when used) an amplitude mask. Missing geometry returns
`INCONCLUSIVE`; geometry is never fabricated from channel order.

## Null controls

The deterministic control bundle records a fixed seed and method for each of:

- Fourier phase randomization;
- channel shuffling;
- time reversal;
- coordinate shuffling;
- contiguous block permutation; and
- stationary circular-shift nulls.

Controls are not interchangeable with a model comparison. A claimed empirical
`PASS` must declare the relevant controls and show that they pass.

## Scope and compatibility

`RunRecordV1`, existing evidence packets, and current runtime contracts remain
the authoritative artifact surfaces. This contract adds semantics and
structured fields without introducing a second orchestration engine. Legacy
numeric topology and `compare_models` entry points remain available, but new
callers should use the explicit result metadata and verdict fields.
