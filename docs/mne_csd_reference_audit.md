# MNE CSD reference audit (Round 6 assertions)

Status: **HOLD / SYNTHETIC_ONLY**. Synthetic sensor montages and stated constants only. No
empirical data, no participant data, no scientific claim. Nothing here promotes any result.

## Reference parity is not scientific validity

Everything below is numerical agreement between this package and the stated formulas, and between
this package and a transcription of the pinned MNE-Python code path. It says nothing about whether
the CSD transform is correct for any EEG recording, head, or montage. "Parity" here means the same
arithmetic as the reference, on synthetic inputs.

## Three evidence classes

| Class | Where | Counted by the Round 6 gate? | What a pass means |
|---|---|---|---|
| Deterministic checks against the formulas and the code-path transcription | `tests/mne_csd_reference_audit/` (gated) | **Yes**. Must collect tests and skip none | Agreement with the stated formulas and with a transcription of the pinned source |
| Frozen fixture of the transcription | `tests/mne_csd_reference_audit/fixtures/mne_code_path_transcription.json`, checked by `test_mne_integration_optional.py` (gated) | **Yes**. Same rule | The transcription and the package still agree with the frozen matrices. **Not** executed MNE output |
| Optional live-MNE comparison | `tests/optional_live_mne/` | **No**. Outside the gate's roots | Only meaningful when MNE 1.13.2 is installed. In this environment it skips, and a skip is **not** evidence |

## What this establishes

1. **Formula-level parity with the pinned MNE source, not execution parity.** The four Round 6
   Legendre constants equal the 50-term series written from the pinned source, to about 1e-15 relative.
   The series was evaluated in pure NumPy, not by running MNE.
2. **The Legendre-ODE identity holds.** For x = cos θ, the sphere Laplacian gives −Δ G = H term by term
   (Δ P_n = −n(n+1) P_n). This checks the m and m−1 exponent convention against a first-principles identity,
   not against MNE. The identity is verified numerically here. The standard DLMF citation was not re-fetched:
   that host is unreachable from this environment.
3. **The KKT and projection forms agree with a transcription of the MNE code path within a conditioning bound.**
   The transcription is a second implementation of the pinned operations, not executed MNE. The package's projection
   form uses TC = Gi·1; MNE 1.13.2 uses TC = Gi.sum(0). They are equal in exact arithmetic, because Gi is symmetric
   in exact arithmetic. Both forms match the transcription within
   10·cond(G+λ²I)·eps on six synthetic montages (`test_kkt_operator.py`). The transcription matches the frozen fixture
   within the same bound (`test_mne_integration_optional.py`). No gated test compares the package directly with the frozen
   matrices: a regenerated fixture is a snapshot, so it constrains the transcription, not the package.
4. **Operator-level properties hold on the same montages**: zero-sum coefficient constraint,
   constant-potential annihilation, exact inverse-square sphere scaling, channel-permutation
   equivariance, and finite output.
5. **Discriminating variants are detected** (λ² placed after inversion; zero-sum constraint dropped),
   so the checks are sensitive to those choices on asymmetric montages.
6. **Refusal behaviour matches MNE 1.13.2 on the inputs listed in the refusal section.** The reference refuses
   what MNE refuses; where it is stricter, that is stated. It does not model MNE's channel picks or bad channels.
7. **The reference package never loads MNE.** Static imports, aliased imports and every dynamic import or dynamic-code
   call are refused by an AST guard over the package source, and an effect check imports every package module in a clean
   process and asserts that MNE is not loaded. Planted loaders fail these checks (mutation checks, below).

## What this does not establish

- **Execution parity with an executed MNE: not established.** MNE is not installed here, and was not
  installed by instruction. The live comparison in `tests/optional_live_mne/` has not been run.
- **Parity with the proposal's custom KKT code: not established.** That code is not in the
  repository on `origin/main` or on any remote branch checked. The Round 6 numbers exist only in the brief.
- **Exact-spline equality: not established.** The constants depend on the 50-term truncation.
- **Scientific validity of CSD for EEG, or of R = 0.095 m as a head or sensor radius.** R is a
  synthetic choice for these checks, not a measured or validated geometry.

## Primary sources and what they support

| Claim | Primary source | Status (2026-10-20) |
|---|---|---|
| Version 1.13.2, sdist SHA-256 `729829e3…5521` | PyPI JSON https://pypi.org/pypi/mne/1.13.2/json | **Re-verified** this session (digest matches) |
| Source file hashes `bcb8b47e…`, `a77c8b02…` | the sdist itself | **Re-verified** from a fresh extraction |
| Tag commit `bf67729b…` | `git ls-remote` on mne-tools/mne-python, verified against the live `v1.13.2` tag on 2026-10-23 | Resolves to `bf67729b805865b5bb0f2f97621e416278efd1b2` |
| Sphere `(x, y, z, r)` with `r` in metres; `"auto"` allowed | sdist docstring, `mne/preprocessing/_csd.py` lines 66-130 | **Re-verified**. The reference refuses `"auto"`, which is stricter |
| `lambda2` in `[0, 1)`, default 1e-5 | sdist `_csd.py` lines 127 and docstring | **Re-verified** |
| `stiffness < 0` refused | sdist `_csd.py` lines 129-131 | **Re-verified** |
| Zero or non-finite positions refused, on raw locations | sdist `_csd.py` line 158 | **Re-verified** |
| `n_legendre_terms` must be at least 1 | sdist `_csd.py` lines 134-136 | **Re-verified** |
| Output unit V/m² | sdist `_csd.py` line 184 (`FIFF_UNIT_V_M2`) | **Re-verified** |
| Bad EEG channels refused; EEG picks only | sdist `_csd.py` lines 108-123 | **Re-verified**. Not modelled by the reference |
| Public API page and defaults | https://mne.tools/stable/generated/mne.preprocessing.compute_current_source_density.html | **Not reachable** from this environment (DNS failure). The sdist docstring is used instead |
| Legendre equation | https://dlmf.nist.gov/14.2 | **Not reachable** from this environment. The identity is verified numerically (below) |
| Perrin et al. (1989) spline formulation, the method MNE cites (`_csd.py` line 67; `interpolation.py` lines 68 and 87) | *Electroencephalogr Clin Neurophysiol* 72(2):184-187, DOI `10.1016/0013-4694(89)90180-6`, from search results. `doi.org` unreachable | **Not accessed**. The printed equations were not read |
| Perrin et al. (1990) corrigendum, "Corrigenda EEG 02274" (*ECN* 76:565) | cited in the header of the CSD Toolbox `CSD.m` (see next row). The toolbox says the 1989 current-density equation had an error that the corrigendum fixes | **Not accessed**. Its content is unknown here, so it is not known whether the corrected equation is the `h_m` form above |
| CSD Toolbox (Kayser; GPL), `func/GetGH.m` and `func/CSD.m`, mirrored at https://github.com/lcnhappe/happe (`Packages/eeglab14_0_0b/CSDtoolbox/func/`) | read through a WebFetch excerpt, not byte-verified. Not run, not transcribed | **Corroborating implementation.** `G` uses `(n(n+1))^m` and `H` uses `(n(n+1))^(m-1)`, both with `1/(4π)`, `n = 1..50` with `P_0` excluded, `m` default 4. `H = −h/4π` with `h` numerator `−(2n+1)`, so `H` is positive. `λ` default 1e-5 is added to the diagonal of `G`. `X = Σ C·H / head` with `head = R²`. Header: "[µV/m²]" for a unit sphere, rescaled to µV/cm² with the radius in cm |
| Kayser & Tenke (2015), "Issues and considerations for using the scalp surface Laplacian in EEG/ERP research: a tutorial review", cited by MNE (`_csd.py` line 67) | search excerpts only, not read in full | **Partial**. Excerpts describe the surface Laplacian as "a truly reference-free technique" (the reference wording in MNE's docstring, `_csd.py` line 70). The PR's "average-referenced" label is therefore a construction label, not a property of the output |
| Other MNE citations: Perrin et al. (1987), Cohen (2014) (`_csd.py` line 67) | not read | **Not used** by this PR |

Convention, stated as formulas and checked against the pinned MNE source and the CSD Toolbox rows above. Implemented
independently. No code is transcribed in `tools/`:

- `g_m(x) = Σ_{n=1..N} (2n+1) / ((n(n+1))^m · 4π) · P_n(x)`, and `h_m(x) = Σ_{n=1..N} (2n+1) / ((n(n+1))^(m−1) · 4π) · P_n(x)`.
  The sum runs over `n = 1..N` inclusive, with no `P_0` term and no minus sign.
- Operator: `G` from cosines of unit sensor vectors. `λ²` is added to the diagonal of `G`. `Gi = G⁻¹`.
  `C = Gi·Z − TC·(1ᵀGi·Z)/sgi`, where `Z = I − 11ᵀ/n`, `sgi = 1ᵀGi1`, and `M = Hᵀ·C / R²`. Output `M·V`.
- **Where the package and MNE differ in ordering.** The package's projection form takes `TC = Gi·1`.
  MNE 1.13.2 computes `TC = Gi.sum(0)` (that is, `Giᵀ·1`). In exact arithmetic these are equal, because `Gi` is
  symmetric. In float64 the difference is exactly `(Gi − Giᵀ)·1`, so it measures the rounding asymmetry of the
  computed `Gi`. Measured on the six montages (snapshot fields `tc_ordering_abs_max`,
  `operator_ordering_rel_to_max`, `gi_asymmetry_abs_max` in `docs/audits/mne_csd_reference_audit.json`):
  the TC difference is 1.8e-12 (`tetrahedron_4`) to 1.5e-10 (`seeded_cap_12`) absolute. `Gi` is asymmetric by up to
  1.3e-9 absolute, on `seeded_cap_12`. The operators differ by at most 3.5e-14 relative. The regression tests bound
  the TC difference at 1e-9 and the operator difference at 1e-13.
- The output unit is recorded as V/m² for positions in metres, following MNE's `FIFF_UNIT_V_M2`. The CSD Toolbox
  header uses the same convention: µV/m² for a unit sphere, and µV/cm² when the radius is given in cm. The unit is
  therefore "input unit / length²" with the radius in the length unit of the positions. It is a surface-Laplacian
  unit, not a physical current density. A physical current density would need a conductivity and layer thickness,
  which this PR does not use.
- Local convention, not a source claim: `R = 0.095 m` is the test radius used throughout this audit.

## Refusal behaviour (L2c)

| Input | MNE 1.13.2 | This reference |
|---|---|---|
| `stiffness < 0` | refuses (`_csd.py:130-131`) | refuses (test `test_negative_stiffness_is_refused_as_mne_refuses_it`) |
| `stiffness` non-finite | propagates NaN | **refuses**. Stricter than MNE, stated here |
| sensor with `np.isclose(loc, 0).all()` on the raw location | refuses (`_csd.py:158`) | refuses, on the raw location before centring (test `test_sensor_at_the_raw_origin_is_refused_as_mne_refuses_it`) |
| `radius <= 0` | refuses (`_csd.py:155`) | refuses, for all three operator forms (test `test_discriminator_variants_refuse_invalid_radius_as_the_reference_does`). Non-finite radius is also refused, which is stricter |
| `lambda2` outside `[0, 1)` | refuses (`_csd.py:127`) | refuses |
| `n_legendre_terms < 1` | refuses (`_csd.py:134-136`) | refuses |
| `n_legendre_terms` not a true integer (bool, float, NaN) | refuses: `_ensure_int` raises `TypeError` for bool and non-integers (`mne/utils/check.py` L25-37, used at `_csd.py:133`) | refuses with `TypeError` (`legendre._series`). Before the 2026-10-21 fix, `True` was accepted as one term |
| `"auto"` sphere | fits a sphere from digitisation | **not accepted**: the reference takes an explicit centre and radius only |
| single channel | a 1×1 operator of zeros (source-derived: with one channel `Z = 0`, so `C = 0`) | **refuses** (`kkt.py`, at least two channels). Stricter than MNE, stated here. Not executed here |
| sensor exactly at a non-zero sphere origin | NaN with a RuntimeWarning (source-derived: `pos / ||pos||` divides by zero after centring) | **refuses** (`kkt.py`, a sensor coincides with the sphere origin). Stricter than MNE, stated here. Not executed here |
| Bad EEG channels, or channel picks | refuses (`_csd.py:108-123`) | **not modelled**: the reference takes positions only |

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

Error is the Frobenius-relative difference from the MNE transcription (not executed MNE). Bound in the test: `10 · cond · eps`.

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
| Package `TC = Gi·1` vs MNE `TC = Gi.sum(0)` | **Ordering difference, not a numerical discrepancy beyond rounding.** The TC difference is `(Gi − Giᵀ)·1`: 1.8e-12 to 1.5e-10 absolute on the six montages. The operator differs by at most 3.5e-14 relative |
| KKT and projection forms vs the MNE transcription | **No discrepancy beyond float64 rounding**, bounded by 10·cond·eps in the tests |
| Legendre-ODE identity | **Holds**: 2.2e-16 relative with an independent H; 8.6e-16 to 2.2e-15 with the package's H |
| Refusal behaviour | **Matches MNE 1.13.2** on the listed inputs; was a gap for three inputs before the 2026-10-19 repair (see the refusal section) |
| Proposal's custom KKT operator vs MNE operator | **Insufficient evidence.** The proposal's code is absent, so it was not compared |
| Operator vs executed MNE `compute_current_source_density` | **Insufficient evidence.** The live comparison has not run |

No mathematical or numerical discrepancy was found in the parts that could be checked.

## Mutation checks (2026-10-20, scratch copies, repository unchanged)

| Mutant | Expected | Observed |
|---|---|---|
| transcription h-exponent drift | transcription and fixture tests fail | 6 failed (fixture reproduction) |
| dynamic import planted in a package module | import guard fails | 1 failed |
| skip marker added to a required file | required-surface marker test fails | 1 failed |
| earlier: proposal constant drift of 5e-16 (absolute) | relative test fails; old absolute test passes | confirmed (see the 2026-10-19 run) |
| `@pytest.mark.skip` decorator in a required file | skip-marker guard fails | 1 failed |
| `pytest.mark.xfail` planted in the guard file itself | no self-exemption: skip-marker guard fails | 1 failed |
| aliased `from importlib import import_module as _imp` inside a package function | import guard fails | 1 failed |
| loader bound to a name inside a package function (`loader = importlib.import_module`) | guard fails | 1 failed |
| computed `getattr(mod, name)` in a package module | guard fails | 1 failed |
| montage added to `MONTAGES` without a frozen matrix | fixture-coverage test fails | 1 failed |
| local variable named `skip` in a required file | no failure (false-positive check) | 1 passed |
| import-time `import mne` in a package module the report never imports | guard and clean-process effect check fail | 2 failed |
| earlier: projection TC scaled by 1.001 | MNE code-path test fails | 4 of 6 failed |
| earlier: h exponent error | ODE and H tests fail | 7 failed |

## Hosted CI status

- **Head `6704614`, hosted run 39315167043 (job 118274623527), 2026-10-19 19:56Z**: `core-tests` failed.
  The round-6 gate recorded `tested_commit_sha` `afc8f86ce8d356b8c35fc6fa078070d98dfec590` for these executions.
  That SHA was not checked against the merge ref. Its `spherical_csd` executions were 81, 18 and 14 collected with
  zero skips. The fourth, `test_mne_integration_optional.py`,
  collected 3 and skipped 3. That was the **only** cause of the gate's `spherical_csd: FAIL`.
- **Superseded simulation (temp commit `e93e9450`, before the 2026-10-20 repair)**: run with main's gate script
  (blob `e1c3d86`), `status PASS`, `unmapped_candidate_paths []`. Its per-file split is not carried forward. The
  split printed here earlier summed to 137, not the stated total of 148, so it could not be relied on.
- **Hosted evidence for each head** is in the PR's check runs, in the `core-tests` job log (the round-6
  `spherical_csd` executions, with `tests_collected`, `skipped`, `failed`, `errors`, `timeouts`, and
  `tested_commit_sha`). This file does not record run IDs, so it does not go stale with each push.
- The owned tests are not in any core batch of `.github/workflows/required-checks.yml`. The round-6 gate is
  the only hosted path that runs them. It is absent at the PR's base `3f3fe85`, present on `origin/main`
  (`bc91af19`), and maps these paths to `spherical_csd`.
- The live-MNE comparison in `tests/optional_live_mne/` is **not** mapped and is not counted.

## Ownership and conflicts

- Not modified: `adapters/mne_csd/`, `dual_engine/`, every path owned by another open PR, and all CI files.
  The adapter wrapping MNE's public function lives in open PR #378 (`batch2/cursor-c-mne-csd-adapter`) and was
  only read.
- Paths owned by this PR: `tools/mne_csd_reference_audit/`, `tests/mne_csd_reference_audit/` (including
  `conftest.py` and `fixtures/`), `tests/optional_live_mne/` (new, outside the gate), `docs/mne_csd_reference_audit.md`,
  and `docs/audits/mne_csd_reference_audit.json`.
- No `.py` file was added under a registered candidate root. The shared helper lives in `conftest.py`, the
  mapped support file, because a new unmapped module there would block the gate.
- Not on `origin/main` (checked 2026-10-19): none of the PR's paths. No collision.

## Reproduce

```
PYTHONPATH=. python -m pytest tests/mne_csd_reference_audit -q            # 158 passed, 0 skipped (gated surface)
PYTHONPATH=. python -m pytest tests/optional_live_mne -q                  # 3 skipped without MNE 1.13.2 (not evidence)
PYTHONPATH=. python -m tools.mne_csd_reference_audit --json-out docs/audits/mne_csd_reference_audit.json
```

The committed snapshot covers the status fields (`HOLD`, `SYNTHETIC_ONLY`), the L1 and L2 entries, and the
L3 status. The L1b, L2b and L2c figures above are measured at audit time and are enforced by test
assertions and bounds. The snapshot command does not regenerate their numerical values.

## Workflow owner: mapping facts (no mapping was edited)

- Implementation paths: `tools/mne_csd_reference_audit/kkt.py`, `legendre.py`, `montages.py`, `pin.py`,
  `report.py`, `__main__.py`.
- Test paths the gate runs, each with zero skips expected: `tests/mne_csd_reference_audit/test_kkt_operator.py`
  (81), `test_legendre_constants.py` (18), `test_isolation_and_pin.py` (41),
  `test_mne_integration_optional.py` (8, deterministic; the name is a legacy mapping key and does not mean optional).
- Command: `python .github/workflows/round6_experimental_tests.py --base <PR base> --head <PR head> --always-component surrogate_nulls --report outputs/round6_experimental_ci_report.json`.
- Expected for the component `mne_csd_reference_audit` on main (gate blob 3e737372): status PASS, four executions, 158 collected (84 / 23 / 43 / 8), 0 skipped, 0 failed, 0 errors, 0 timeouts. The live test is external (`optional-eeg-suite`) and is not counted.
- Not mapped and not counted: `tests/optional_live_mne/test_mne_csd_live_parity.py`. It must not be added to a
  required surface unless CI installs MNE 1.13.2.
- Renaming `test_mne_integration_optional.py` requires a mapping change, which belongs to the workflow owner.

## Regenerate the frozen fixture

The fixture is produced by the transcription in `conftest.py`, never by the package. The recipe, run from the
repository root, loads `conftest.py` directly and writes the JSON. It is not a committed tool, because a new `.py`
under a mapped root would block the gate:

```
python - <<'PY'
import importlib.util, json, sys
import numpy as np
sys.path.insert(0, ".")
from tools.mne_csd_reference_audit import pin
from tools.mne_csd_reference_audit.montages import MONTAGES
spec = importlib.util.spec_from_file_location("c", "tests/mne_csd_reference_audit/conftest.py")
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
R, L2 = 0.095, 1e-5
out = {"schema": "NTS.MNECSDTranscriptionFixture.v1", "status": "HOLD", "evidence_class": "SYNTHETIC_ONLY",
       "producer": "tests/mne_csd_reference_audit/conftest.py::mne_code_path: a transcription of the pinned MNE 1.13.2 code path. NOT executed MNE output. Not generated by the candidate package.",
       "mne_version": pin.MNE_VERSION, "mne_tag_commit": pin.MNE_TAG_COMMIT, "sdist_sha256": pin.MNE_SDIST_SHA256,
       "source_sha256": dict(pin.MNE_SOURCE_FILES),
       "source_lines": {"mne/preprocessing/_csd.py": "26-50 (_prepare_G, _compute_csd); 158 (zero-position refusal)",
                        "mne/channels/interpolation.py": "20-37 (_calc_h), 40-62 (_calc_g)"},
       "radius_m": R, "lambda2": L2, "stiffness": 4, "n_legendre_terms": 50, "montages": {}}
for name in sorted(MONTAGES):
    pos = R * np.asarray(MONTAGES[name](), dtype=float)
    M, G = c.mne_code_path(pos, R, L2)
    out["montages"][name] = {"n_channels": len(pos), "positions_m": pos.tolist(),
                             "cond_G_reg": float(np.linalg.cond(G)), "matrix": M.tolist()}
open("tests/mne_csd_reference_audit/fixtures/mne_code_path_transcription.json", "w").write(
    json.dumps(out, indent=1, sort_keys=True) + "\n")
PY
```

## Limitations

- Pure NumPy reference, written from the formulas and checked against a transcription of the pinned code path.
  MNE was not executed.
- The proposal's KKT code is not available, so the claim "the proposal's operator equals MNE's" is not tested.
- Six synthetic montages only. No recording, no real montage, no empirical result. R = 0.095 m is a synthetic choice.
- Output units are 1/length² times the input unit. V/m² holds only for positions in metres. Not validated
  against a recording.
- The frozen fixture is a transcription, not MNE output. It guards the transcription against drift only.
- The import guard is an AST denylist over the package source, plus an effect check that imports every package module
  in a clean process and asserts that MNE is not loaded. The denylist refuses imports naming mne, the dynamic loaders
  and runpy or builtins, any reference to them (called or bound to a name), and getattr with a computed or denied
  name. A load that runs only when a function is called, through a name the denylist does not list, is not detected.
  The package uses none of the denied names today.

## Next step (owner decision)

Run `tests/optional_live_mne/` in an environment where MNE 1.13.2 is installed, and compare against the pinned
operator. This needs an installed MNE, which this audit did not install.
