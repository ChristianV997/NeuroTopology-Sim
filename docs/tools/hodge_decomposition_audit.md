# Round-6 Hodge Decomposition Numerical Audit

Status: **HOLD / SYNTHETIC_ONLY**. Independent synthetic audit of 2D cochain /
weighted Hodge–Helmholtz identities on tiny oriented meshes.

This lane does **not**:

- validate Delaunay geometry or finite-jitter mesh quality (separate lane)
- edit winding-charge metric implementations
- import or claim pass/fail for open PR `#385` (`experimental/phase_cochain_reference/`)
- emit scientific VALIDATED claims

Owned paths:

- `tools/hodge_decomposition_audit/`
- `tests/tools/hodge_decomposition_audit/`
- `docs/tools/hodge_decomposition_audit.md`

## Fixtures and boundary conditions

| Fixture | Boundary class | Notes |
|---|---|---|
| `disk_single_triangle` | disk_with_boundary | One face; outer 3-cycle is boundary |
| `disk_quad_fan` | disk_with_boundary | Four triangles; outer 4-cycle boundary |
| `closed_cycle_complex` | closed_cycle_complex | C3 1-skeleton, zero triangles; harmonic not assumed zero |
| `annulus_like_band` | annulus_like | Band with b1 > 0; harmonic not assumed zero |

## Algebraic vs numerical

**Algebraic (exact for this incidence construction):**

- `d1 @ d0 == 0`
- dimension equations for `d0`, `d1`
- raw integer face charges from `d1 @ omega` independent of Hodge edge weights `W1`

**Numerical (tolerances depend on conditioning / scale):**

- weighted orthogonality residuals after floating-point solves
- energy closure and reconstruction residuals
- harmonic-component magnitude thresholds
- condition numbers of `L0 = d0ᵀ W1 d0` and `M = d1 W1⁻¹ d1ᵀ`

Ill-conditioned or non-positive weights are **rejected** with diagnostics
(`REJECTED_ILL_CONDITIONED`) rather than silently inverted.

## CLI

```bash
python -m tools.hodge_decomposition_audit \
  --output-json /tmp/hodge_audit.json \
  --output-md /tmp/hodge_audit.md
```

## Proposal reference

PR `#385` owns the proposed reference implementation. This audit builds an
independent fixture oracle on `main` and sets `proposal_claimed_passed: false`.
