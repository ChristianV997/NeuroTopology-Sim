# MNE CSD reference audit (Round 6 assertions)

Status: **HOLD / SYNTHETIC_ONLY**. Synthetic sensor montages and stated constants only. No
empirical data, no participant data, no scientific claim. Nothing here promotes any result.

## What this establishes

1. **Coefficient parity: established.** The four Round 6 Legendre constants equal the MNE-convention
   50-term series to about 1e-15 (relative), evaluated independently in pure NumPy.
2. **KKT and projection forms of the average-referenced operator agree numerically (1e-13).**
   This is an algebraic equivalence check of the MNE-path construction, not an execution check.
3. **Operator-level properties hold on six synthetic montages**: zero-sum coefficient constraint,
   constant-potential annihilation, exact inverse-square sphere scaling, channel-permutation
   equivariance, and finite output.
4. **Discriminating variants are detected** (λ² placed after inversion; zero-sum constraint dropped),
   so the checks are sensitive to those choices on asymmetric montages.

## What this does not establish

- **Full-operator parity with an executed MNE: not established.** MNE is not installed here and was
  not installed by instruction. The optional integration test skips.
- **Parity with the proposal's custom KKT code: not established.** That code is not in the
  repository on `origin/main` or on any remote branch. The Round 6 numbers exist only in the brief.
- **Exact-spline equality: not established.** The constants depend on the 50-term truncation.

## Levels executed

| Level | Status |
|---|---|
| L1 Legendre constants (pure NumPy) | **executed** (4 constants, plus a `numpy.polynomial.legendre.legval` cross-check) |
| L2 operator algebra and properties (pure NumPy) | **executed** (6 montages, 83 tests in the package) |
| L3 MNE execution parity | **not executed**. Integration test written with `importorskip` and a version guard. Only the skip path ran |

## Pinned MNE source (verified, not summarised)

- Version `1.13.2`, tag `v1.13.2`, tag commit `bf67729b805865b5bb0f2f97621e416278efd1b2`
  (`git ls-remote` of `refs/tags/v1.13.2` on `mne-tools/mne-python`; lightweight tag).
- sdist `mne-1.13.2.tar.gz`, SHA-256 `729829e35010a7273cce8608d61d930c973fbead6edc1a70316c01e3a5551521`.
  Downloaded and the local digest matched the PyPI digest exactly.
- Source files read from the verified sdist:
  - `mne/channels/interpolation.py` SHA-256 `bcb8b47e34eaa7fe002484662882e9fb5cf64d54c18e92611a2d1e9fd44936cd`
  - `mne/preprocessing/_csd.py` SHA-256 `a77c8b02cf4f2465a43f994bf4dd1efdc7250ca274957f7b77af37057f51541f`
- Licence: BSD-3-Clause. The reference package copies no MNE code.

Convention, stated as formulas (read from the pinned source, implemented independently):

- `g_m(x) = Σ_{n=1..N} (2n+1) / ((n(n+1))^m · 4π) · P_n(x)`, and `h_m(x) = Σ_{n=1..N} (2n+1) / ((n(n+1))^(m−1) · 4π) · P_n(x)`.
  The sum runs over `n = 1..N` inclusive, with no `P_0` term and no minus sign.
- Operator: `G` from cosines of unit sensor vectors; `λ²` added to the diagonal of `G`; `Gi = G⁻¹`;
  `TC = Gi·1`; `sgi = 1ᵀGi1`; `C = Gi·Z − TC·(1ᵀGi·Z)/sgi`, where `Z = I − 11ᵀ/n`;
  `M = Hᵀ·C / R²`; output `M·V`. The output unit is recorded as V/m² for positions in metres.

## Results

### Coefficient parity (N = 50, the default)

| constant | claimed (brief) | computed N=50 | abs diff | rel diff | N=4000 shift |
|---|---|---|---|---|---|
| G(1) | 0.0152607616970611 | 0.01526076169706111 | 6.94e-18 | 4.55e-16 | 1.51e-12 |
| G(0) | -0.000151919699050514 | -0.0001519196990505138 | 1.63e-19 | 1.07e-15 | 9.10e-15 |
| H(1) | 0.0321583490430606 | 0.03215834904306064 | 4.16e-17 | 1.29e-15 | 5.88e-09 |
| H(0) | -0.000891062383022325 | -0.0008910623830223247 | 3.25e-19 | 3.65e-16 | 2.43e-11 |

The "N=4000 shift" column is the change if the series is extended. It is not an error. It shows
that `H(1)` depends on the truncation at about 1.8e-7 relative. Coefficient parity therefore holds
for the 50-term MNE default, not for the exact infinite series.

### Operator checks (R = 0.095 m, λ² = 1e-5, m = 4)

| montage | n | cond(G+λ²I) | KKT vs projection | Σ-constraint residual | constant→0 | R² scaling | permutation | disc: λ² after inv | disc: no Σ-constraint |
|---|---|---|---|---|---|---|---|---|---|
| tetrahedron_4 | 4 | 271 | 7.4e-15 | 0 | 1.6e-16 | 2.1e-16 | 8.2e-17 | 4.9e-04 | 7.6e-15 |
| octahedron_6 | 6 | 1.15e3 | 4.0e-15 | 5.7e-14 | 2.0e-15 | 0 | 1.9e-15 | 7.3e-03 | 3.7e-15 |
| ring_apex_9 | 9 | 2.24e3 | 9.7e-14 | 1.9e-12 | 1.9e-14 | 1.1e-13 | 5.7e-14 | 3.6e-01 | 4.1e-01 |
| seeded_cap_7 | 7 | 2.48e3 | 2.1e-14 | 2.3e-13 | 1.0e-14 | 8.2e-14 | 3.8e-14 | 4.0e-01 | 5.0e-01 |
| seeded_cap_12 | 12 | 7.43e3 | 8.2e-14 | 5.5e-12 | 3.6e-14 | 1.1e-13 | 1.4e-13 | 2.6e+00 | 4.4e-01 |
| near_coincident_6 | 6 | 4.92e3 | 6.6e-14 | 1.1e-13 | 7.0e-14 | 3.9e-14 | 9.0e-14 | 7.8e+00 | 4.6e-01 |

Values are relative to `max|M|`. The duplicate-sensor case raises `LinAlgError` at `λ² = 0` and is
finite at `λ² = 1e-5`.

The zero-sum constraint is redundant on the symmetric tetrahedron and octahedron (discriminator
≈ 1e-15), so only the asymmetric montages test it.

## Discrepancy classification

| Item | Classification |
|---|---|
| Round 6 constants vs MNE-convention N=50 series | **No discrepancy** (matches to ~1e-15). Sign convention agrees: `H(1) > 0`, no minus sign in MNE |
| 50-term constants vs exact infinite series | **Truncation-specific, not a parity failure.** `H(1)` shifts 1.8e-7 relative at N=4000 |
| KKT form vs MNE-path projection form | **No discrepancy** (mathematical equivalence, verified to 1e-13) |
| Proposal's custom KKT operator vs MNE operator | **Insufficient evidence.** The proposal's code is absent, so it was not compared |
| Operator vs executed MNE `compute_current_source_density` | **Insufficient evidence.** L3 not executed |
| API / version | Pinned 1.13.2. The public names `compute_current_source_density`, `RawArray`, and `create_info` appear in the pinned sdist's `.pyi` stubs. The keyword signature used by the integration test is in `mne/preprocessing/_csd.py`. Not executed |

No mathematical or numerical discrepancy was found in the parts that could be checked.

## Ownership and conflicts

- Not modified: `adapters/mne_csd/`, `dual_engine/`, and every path owned by an open PR. The adapter
  wrapping MNE's public function lives in open PR #378 (`batch2/cursor-c-mne-csd-adapter`) and was
  only read.
- New paths only: `tools/mne_csd_reference_audit/`, `tests/mne_csd_reference_audit/`,
  `docs/mne_csd_reference_audit.md`, `docs/audits/mne_csd_reference_audit.json`.
- No path collision on `origin/main`.

## Reproduce

```
PYTHONPATH=. python -m pytest tests/mne_csd_reference_audit -q       # 83 passed, 3 skipped (MNE absent)
PYTHONPATH=. python -m tools.mne_csd_reference_audit --json-out docs/audits/mne_csd_reference_audit.json
```

## Limitations

- Pure NumPy reference, written from the formulas. MNE was not executed.
- The proposal's KKT code is not available, so the claim "the proposal's operator equals MNE's" is not tested.
- Six synthetic montages only. No recording, no real montage, no empirical result.
- Output units are 1/length² times the input unit. V/m² holds only for positions in metres. Not validated
  against a recording.
- The integration test's body has not been executed.

## Next step (owner decision)

Run the optional integration test in an environment where MNE 1.13.2 is installed, and compare
against the pinned operator. This needs an installed MNE, which this audit did not install.
