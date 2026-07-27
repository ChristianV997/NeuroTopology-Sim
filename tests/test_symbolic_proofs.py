import numpy as np
from sim.pitnn.exceptional_points_fast import optimize_reduced_ep
from sim.pitnn.symbolic_proofs import closed_form_residual, ep_pump_roots, reduced_hamiltonian_n2, reduced_hamiltonian_n4

def test_closed_form_ep_roots_and_residuals_are_machine_precise():
    loss, coupling, detuning = 5.0, 1.25, 0.75
    expected = ep_pump_roots(loss, coupling, detuning)
    result = optimize_reduced_ep(loss, coupling, detuning)
    np.testing.assert_allclose(result["pump_roots_s"], expected, atol=1e-12, rtol=0.0)
    assert max(abs(value) for value in result["residuals"]) < 1e-12
    assert all(abs(closed_form_residual(root, loss, coupling, detuning)) < 1e-12 for root in expected)

def test_reduced_matrices_have_expected_shapes():
    assert reduced_hamiltonian_n2(3.0, 5.0, 1.0).shape == (2,2)
    assert reduced_hamiltonian_n4(3.0, 5.0, 1.0).shape == (4,4)
