# Physical Corrections Phase 1

Implemented corrections for the PITNN stack:

- `tryptophan_lindblad.py` now includes a super-Ohmic phonon spectral density,
  positive pure-dephasing dissipator, and phonon-limited effective decay widths.
  The lifetime enhancement is finite and no longer an unbounded radiative-vacuum
  artifact.
- `microtubule_3d.py` exposes explicit axial toroidal PBC, wrapped parallel
  bonds, an axial period, and minimum-image DMI displacements.
- `rg_coarse_graining.py` provides Kadanoff block-spin decimation and temporal
  rescaling `dt' = b^z dt`.
- `mumax3_macro_tda.py` provides `invert_rg_magnetization` as the TDA handoff.
- `exceptional_points_fast.py` provides full `N x N` spectrum construction,
  global closest-pair diagnostics, and a bounded full-spectrum optimizer.

Verification:

```text
4 passed  (new physical-correction tests)
5 passed  (legacy Lindblad/microtubule/PITNN plus new tests)
```

The empirical `K > 100` gate was not changed. The full-spectrum result is a
network spectral-gap diagnostic, not evidence for a biological phase transition.
