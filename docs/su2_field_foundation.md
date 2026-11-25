# General SU(2) field foundation

`field_theory.su2` is a synthetic, static, three-dimensional field representation.
It uses unit four-vectors `n` and the convention `U = n0 I + i sum(na sigma_a)`.
The three leading array axes are spatial; a time axis is not accepted. Grid spacing
and length units are explicit metadata. The `fixed_vacuum` boundary label records
the intended model boundary; the general field constructor does not enforce the
field value on a boundary. The hedgehog initializer does have vacuum-valued faces.

The compact C1 radial profile used by `hedgehog` is an initial configuration, not a
numerical solution of the Skyrme equations. No energy, topological charge, neural
interpretation or evidence of consciousness is calculated by this package.

Run: `python -m pytest tests/test_su2_field_foundation.py -q`.

