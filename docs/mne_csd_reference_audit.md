# MNE CSD reference audit (Round 6 assertions)

Status: **HOLD / SYNTHETIC_ONLY**. Synthetic sensor montages and stated constants only. No
empirical data, no participant data, no scientific claim. Nothing here promotes any result.

## Reference parity is not scientific validity

Everything below is numerical agreement between this package and the stated formulas, and between
this package and a transcription of the pinned MNE-Python code path. It says nothing about whether
the CSD transform is correct for any EEG recording, head, or montage. "Parity" here means the same
arithmetic as the reference, on synthetic inputs.

## What this establishes

1. **Formula-level parity with the pinned MNE source, not execution parity.** The four Round 6
   Legendre constants equal the 50-term series written from the pinned source, to about 1e-15 relative.
   The series was evaluated in pure NumPy, not by running MNE.
2. **The Legendre-ODE identity holds.** For x = cos θ, the sphere Laplacian gives −Δ G = H term by term
   (Δ P_n = −n(n+1) P_n). This checks the m and m−1 exponent convention against a first-principles identity,
   not against MNE. The residual is rounding only (see the Legendre-ODE section for the evaluator-dependent figures).
3. **The KKT and projection forms agree with the MNE code path within a conditioning bound.** The
   package's projection form uses TC = Gi·1; MNE 1.13.2 uses TC = Gi.sum(0). They are equal in exact
   arithmetic, because Gi is symmetric. Both forms match a transcription of the MNE code path within
   10·cond(G+λ²I)·eps on six synthetic montages.
4. **Operator-level properties hold on the same montages**: zero-sum coefficient constraint,
   constant-potential annihilation, exact inverse-square sphere scaling, channel-permutation
   equivariance, and finite output.
5. **Discriminating variants are detected** (λ² placed after inversion; zero-sum constraint dropped),
   so the checks are sensitive to those choices on asymmetric montages.
6. **Refusal behaviour matches MNE 1.13.2 on the inputs listed in the refusal section.** The reference refuses
   what MNE refuses; where it is stricter, that is stated.

## What this does not establish

- **Execution parity with an executed MNE: not established.** MNE is not installed here, and was not
  installed by instruction. The optional integration test skips. Its body has not been run.
- **Parity with the proposal's custom KKT code: not established.** That code is not in the
  repository on `origin/main` or on any remote branch checked. The Round 6 numbers exist only in the brief.
- **Exact-spline equality: not established.** The constants depend on the 50-term truncation.
- **Scientific validity of CSD for EEG, or of R = 0.095 m as a head or sensor radius.** R is a
  synthetic choice for these checks, not a measured or validated geometry.

## Levels executed

| Level | Status |
|---|---|
| L1 Legendre constants vs the pinned-source series (pure NumPy, package and `legval`) | **executed** |
| L1b Legendre-ODE identity −ΔG = H, with the package's H (pure NumPy) | **executed** |
| L2 operator algebra and properties (pure NumPy, six montages) | **executed** |
| L2b KKT and projection vs a transcription of the MNE code path (pure NumPy) | **executed** |
| L2c Refusal behaviour on inputs MNE refuses (pure NumPy) | **executed** |
| L3 MNE execution parity | **not executed**. The integration test is written with `importorskip` and a version guard. Only the skip path has run |

Current result of the focused suite: **113 passed, 3 skipped** (the 3 are the L3 cases, skipped because
MNE is not importable).

## Pinned MNE source and provenance

| Item | Value | Status (2026-10-19) |
|---|---|---|
| Version | 1.13.2 | Recorded 2026-10-17 from PyPI |
| sdist SHA-256 | `729829e35010a7273cce8608d61d930c973fbead6edc1a70316c01e3a5551521` | **Re-verified** against https://pypi.org/pypi/mne/1.13.2/json and against the local sdist |
| Tag `v1.13.2` commit | `bf67729b805865b5bb0f2f97621e416278efd1b2` | Recorded 2026-10-17 by `git ls-remote`. **Not re-verified** here: mne-tools/mne-python is outside this session's repository access |
| `mne/channels/interpolation.py` SHA-256 | `bcb8b47e34eaa7fe002484662882e9fb5cf64d54c18e92611a2d1e9fd44936cd` | **Re-verified** from a fresh extraction |
| `mne/preprocessing/_csd.py` SHA-256 | `a77c8b02cf4f2465a43f994bf4dd1efdc7250ca274957f7b77af37057f51541f` | **Re-verified** from a fresh extraction |
| Public names in `.pyi` stubs | `compute_current_source_density`, `RawArray`, `create_info` | **Re-verified**: each appears in one stub file in the sdist |
| `compute_current_source_density` keywords | `lambda2=1e-5`, `stiffness=4`, `n_legendre_terms=50`, `copy=True`, `verbose` | **Re-verified** from `mne/preprocessing/_csd.py` |
| Licence | BSD-3-Clause | Recorded; the reference package copies no MNE code |

Convention, stated as formulas (read from the pinned source, implemented independently):

- `g_m(x) = Σ_{n=1..N} (2n+1) / ((n(n+1))^m · 4π) · P_n(x)`, and `h_m(x) = Σ_{n=1..N} (2n+1) / ((n(n+1))^(m−1) · 4π) · P_n(x)`.
  The sum runs over `n = 1..N` inclusive, with no `P_0` term and no minus sign.
- Operator: `G` from cosines of unit sensor vectors. `λ²` is added to the diagonal of `G`. `Gi = G⁻¹`.
  `C = Gi·Z − TC·(1ᵀGi·Z)/sgi`, where `Z = I − 11ᵀ/n`, `sgi = 1ᵀGi1`, and `M = Hᵀ·C / R²`. Output `M·V`.
- **Where the package and MNE differ in ordering.** The package's projection form takes `TC = Gi·1`.
  MNE 1.13.2 computes `TC = Gi.sum(0)` (that is, `Giᵀ·1`). These are the same in exact arithmetic. In
  float64 they differ in TC by about 1.5e-10 to 1.7e-10 absolute on the six montages, depending on how `G` is
  assembled. The operators differ by at most 4.4e-13 relative. The regression test bounds the operator
  difference. It does not assert the TC difference itself.
- The output unit is recorded as V/m² for positions in metres, following MNE's `FIFF_UNIT_V_M2`.

## Refusal behaviour (L2c)

| Input | MNE 1.13.2 | This reference |
|---|---|---|
| `stiffness < 0` | refuses (`_csd.py:130-131`) | refuses (test `test_negative_stiffness_is_refused_as_mne_refuses_it`) |
| `stiffness` non-finite | propagates NaN | **refuses**. Stricter than MNE, stated here |
| sensor with `np.isclose(loc, 0).all()` on the raw location | refuses (`_csd.py:158`) | refuses, on the raw location before centring (test `test_sensor_at_the_raw_origin_is_refused_as_mne_refuses_it`) |
| `radius <= 0` | refuses (`_csd.py:155`) | refuses, for all three operator forms (test `test_discriminator_variants_refuse_invalid_radius_as_the_reference_does`). Non-finite radius is also refused, which is stricter |
| `lambda2` outside `[0, 1)` | refuses (`_csd.py:127`) | refuses |
| `n_legendre_terms < 1` | refuses (`_csd.py:134-136`) | refuses |

Three of these were gaps before the 2026-10-19 repair: negative stiffness, raw-origin sensors, and the radius guard
in the two discriminator variants. Each has a regression test that fails on the pre-repair code.

## Results

### Coefficient parity (N = 50, the default)

| constant | claimed (brief) | computed N = 50 (package recurrence) | abs diff | rel diff | \|N=4000 − N=50\| abs | \|N=4000 − N=50\| rel |
|---|---|---|---|---|---|---|
| G(1) | 0.0152607616970611 | 0.01526076169706111 | 6.94e-18 | 4.55e-16 | 1.51e-12 | 9.87e-11 |
| G(0) | -0.000151919699050514 | -0.0001519196990505138 | 1.63e-19 | 1.07e-15 | 9.10e-15 | 5.99e-11 |
| H(1) | 0.0321583490430606 | 0.03215834904306064 | 4.16e-17 | 1.29e-15 | 5.88e-09 | 1.83e-07 |
| H(0) | -0.000891062383022325 | -0.0008910623830223247 | 3.25e-19 | 3.65e-16 | 2.43e-11 | 2.72e-08 |

The last two columns show the change if the series is extended to N = 4000. They are not errors. The
relative column is the one that matters: `H(1)` moves about 1.8e-7 relative. Coefficient parity holds for
the 50-term MNE default, not for the exact infinite series.

Evaluator dependence: the same constants evaluated with `numpy.polynomial.legendre.legval` give relative
differences of 5.7e-16, 7.1e-16, 8.6e-16 and 3.7e-16. The differences are at the 1e-16 level, and the test
bound is 1e-14 relative. The bound is justified because the brief gives 15 significant digits, which alone
allows up to ~3.3e-15 relative (for G(0)).

### Legendre-ODE identity

`−Δ G = H` with `Δf = (1−x²)f'' − 2xf'`, on 401 points in [−0.999, 0.999]. The residual is relative to `max|H|`.

| Evaluation of H | N = 50 | N = 200 |
|---|---|---|
| independent `legval` evaluation of the same formula | 2.2e-16 | 2.2e-16 |
| package `h_function` (recurrence) | 8.6e-16 | 2.2e-15 |

The test uses the package's H at N = 50 and asserts `< 1e-13`. The N = 200 package-H figure is measured
but not asserted.

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

### Code-path comparison against the MNE transcription

Error is the Frobenius-relative difference from the MNE code path. Bound in the test: `10 · cond · eps`.

| montage | n | cond(G+λ²I) | cond·eps | kkt vs MNE path | projection vs MNE path | max error / (cond·eps) |
|---|---|---|---|---|---|---|
| tetrahedron_4 | 4 | 2.71e2 | 6.0e-14 | 4.8e-15 | 6.1e-15 | 0.10 |
| octahedron_6 | 6 | 1.15e3 | 2.5e-13 | 1.2e-14 | 1.3e-14 | 0.05 |
| ring_apex_9 | 9 | 2.24e3 | 5.0e-13 | 4.4e-13 | 4.0e-13 | 0.88 |
| seeded_cap_7 | 7 | 2.48e3 | 5.5e-13 | 3.0e-13 | 3.1e-13 | 0.56 |
| seeded_cap_12 | 12 | 7.43e3 | 1.7e-12 | 4.0e-13 | 3.7e-13 | 0.25 |
| near_coincident_6 | 6 | 4.92e3 | 1.1e-12 | 4.1e-13 | 4.0e-13 | 0.38 |

The worst ratio is 0.88, so the bound holds with about an order of magnitude to spare. The test is not
loosened to pass; the existing `1e-10` KKT-vs-projection test is unchanged.

## Discrepancy classification

| Item | Classification |
|---|---|
| Round 6 constants vs the pinned-source N = 50 series | **No discrepancy** (matches to ~1e-15 relative). Sign convention agrees: `H(1) > 0`, no minus sign |
| 50-term constants vs exact infinite series | **Truncation-specific, not a parity failure.** `H(1)` shifts 1.8e-7 relative at N = 4000 |
| Package `TC = Gi·1` vs MNE `TC = Gi.sum(0)` | **Ordering difference, not a numerical discrepancy beyond rounding.** TC differs by about 1.5e-10 to 1.7e-10 absolute; the operator by at most 4.4e-13 relative |
| KKT and projection forms vs the MNE code path | **No discrepancy beyond float64 rounding**, bounded by 10·cond·eps in the tests |
| Legendre-ODE identity | **Holds**: 2.2e-16 relative with an independent H; 8.6e-16 to 2.2e-15 with the package's H |
| Refusal behaviour | **Matches MNE 1.13.2** on the listed inputs; was a gap for three inputs before the 2026-10-19 repair (see the refusal section) |
| Proposal's custom KKT operator vs MNE operator | **Insufficient evidence.** The proposal's code is absent, so it was not compared |
| Operator vs executed MNE `compute_current_source_density` | **Insufficient evidence.** L3 not executed |

No mathematical or numerical discrepancy was found in the parts that could be checked.

## Hosted CI status (checked 2026-10-19)

- The owned tests are not in any core batch in `.github/workflows/required-checks.yml`, on either the PR's
  base (`3f3fe85`) or current `origin/main` (`bc91af19`).
- The round-6 gate (`.github/workflows/round6_experimental_tests.py`) is absent at the PR's base `3f3fe85`.
  It is present on `origin/main`, where it maps these paths to the `spherical_csd` component.
- Run locally with main's gate, the component reports **FAIL**, not pass: the three optional MNE integration
  cases are skipped, and the gate fails any skip. This is a policy question for the workflow owner, not a
  test defect.
- No hosted run has executed the exact paths of this PR.

## Ownership and conflicts

- Not modified: `adapters/mne_csd/`, `dual_engine/`, and every path owned by an open PR. The adapter wrapping
  MNE's public function lives in open PR #378 (`batch2/cursor-c-mne-csd-adapter`) and was only read.
- New paths only: `tools/mne_csd_reference_audit/`, `tests/mne_csd_reference_audit/`,
  `docs/mne_csd_reference_audit.md`, `docs/audits/mne_csd_reference_audit.json`.
- Not on `origin/main` (checked 2026-10-19): none of the PR's paths. No collision.

## Reproduce

```
PYTHONPATH=. python -m pytest tests/mne_csd_reference_audit -q       # 113 passed, 3 skipped (MNE absent)
PYTHONPATH=. python -m tools.mne_csd_reference_audit --json-out docs/audits/mne_csd_reference_audit.json
```

The committed snapshot covers the status fields (`HOLD`, `SYNTHETIC_ONLY`), the L1 and L2 entries, and the
L3 status. The L1b, L2b and L2c figures above are measured at audit time and are enforced by test
assertions and bounds. The snapshot command does not regenerate their numerical values.

## Limitations

- Pure NumPy reference, written from the formulas and checked against a transcription of the pinned code path.
  MNE was not executed.
- The proposal's KKT code is not available, so the claim "the proposal's operator equals MNE's" is not tested.
- Six synthetic montages only. No recording, no real montage, no empirical result. R = 0.095 m is a synthetic choice.
- Output units are 1/length² times the input unit. V/m² holds only for positions in metres. Not validated
  against a recording.
- The integration test's body has not been executed.
- The static import guard matches source text. It catches the forms listed in its tests, not every possible
  indirection.

## Next step (owner decision)

Run the optional integration test in an environment where MNE 1.13.2 is installed, and compare against the
pinned operator. This needs an installed MNE, which this audit did not install.
