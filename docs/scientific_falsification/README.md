# Scientific falsification contract

This directory documents the evidence boundary for the PITNN comparison. The
implementation is an analysis aid; it does not confirm biology, consciousness,
or a Wilson--Cowan mechanism.

## Verdicts

- `PASS` is reserved for a finite **formal** Bayes factor `K > 100` from a
  declared likelihood or marginal-likelihood calculation, with valid empirical
  data, complete provenance, interpretable analysis, sufficient effective
  sample size, declared controls that pass, and known multiplicity handling.
- `NOT_SUPPORTED` means the input is usable but the evidence does not satisfy
  that gate. This includes all synthetic, fixture, null, and surrogate data;
  proxy evidence even when its numeric K exceeds 100; and formal K values at or
  below 100. The boundary is strict: `K == 100` is not a PASS.
- `INCONCLUSIVE` means the contract cannot interpret the result: missing or
  malformed data, constant/degenerate features, insufficient paired subjects or
  effective samples, incomplete provenance, unknown multiplicity, failed
  identifiability, or unsupported model comparison.
- `ERROR` means execution or contract failure, rather than scientific support.

The legacy `bayes_factor` field remains numeric for existing callers. The
canonical field is `k_value`; an unavailable K is represented by `null` in the
structured result and by `0.0` only in the compatibility alias.

## Proxy versus formal evidence

`bayes_factor_proxy_from_rss` computes an information-criterion evidence ratio
from RSS and model parameter counts. It exposes AIC, AICc, and BIC, with BIC
selected by default for a stronger complexity penalty. This is a proxy, not a
formal Bayes factor: it does not integrate a likelihood over parameter priors,
and it cannot produce `PASS`.

`bayes_factor_from_marginal_likelihoods` is the formal method. It accepts
positive finite marginal likelihoods and explicit model priors, records the
assumptions, and returns the exact ratio without clipping or rescaling. A
regression surrogate is not a Wilson--Cowan likelihood; the comparison labels
that arm `wilson_cowan_proxy_regression` and
`likelihood_status: not_implemented`.

No implementation path forces, inflates, clips, or rescales K to cross the
threshold. Overflow or invalid evidence is represented as a null K with an
error.

## Required evidence metadata

Structured comparison results include data mode, provenance status, sample and
effective sample counts, feature count, model parameter counts, likelihood
method, selected evidence metric, null/control status, multiplicity status,
preregistration status, uncertainty, warnings, and errors. Empirical inputs
must identify a dataset, source, source file/path or URI, and positive sample
rate. A declared number of tests greater than one requires Bonferroni or Holm
correction; an unknown test count is not silently treated as one test.

## Deterministic controls

`generate_null_controls` produces seeded, labelled controls for flat signals,
independent Gaussian noise, Fourier phase randomization, condition-label
permutation, and a stationary block/circular-shift surrogate. Each control
records its method and seed. Repeating a seed must reproduce the control. Null
and synthetic runs are useful for calibration and regression tests but cannot
support an empirical PASS.

## Topology separation

Graph beta-1 (cycle rank), coordinate-dependent spatial winding/topological
charge, and scalar chirality are distinct observables. They are exported under
`graph_beta1`, `spatial_winding_q`, and `scalar_chirality` and are never
converted into one another by the falsification layer.

## Scientific limitations

The current comparison remains exploratory. Without a validated generative
likelihood, calibrated priors, preregistered estimands, and independent
replication, an information-criterion result is only a model-comparison
proxy. A `PASS` from a future formal method would support the declared
statistical comparison only; it would not establish a biological mechanism or
biological confirmation.

## Consumer migration

Downstream scripts and dashboards must stop treating the legacy numeric
`bayes_factor` field as a formal-evidence indicator. It remains available as a
deprecated compatibility alias so old readers do not break, but its meaning is
ambiguous by design. New consumers should read the semantic envelope:

- `evidence_method` and `evidence_kind` (`proxy` or `formal`)
- `data_status` / `empirical_status`
- `verdict` and `scientific_eligibility`
- `proxy_value` for an information-criterion/RSS proxy
- `formal_bayes_factor` for a validated marginal-likelihood result
- `reason_codes` for machine-readable explanations

Use `serialize_falsification_result` when emitting JSON from the falsification
module. It keeps the old numeric field, adds the semantic fields, and carries a
warning that the numeric alias must not be interpreted as formal evidence.
Missing formal evidence is serialized as JSON `null`; it is not replaced with
zero or another sentinel that could be mistaken for a measured Bayes factor.

The current classical arm is explicitly
`wilson_cowan_proxy_regression` with `likelihood_status: not_implemented`.
Downstream code must not display it as a fitted Wilson--Cowan likelihood or as
biological confirmation.
