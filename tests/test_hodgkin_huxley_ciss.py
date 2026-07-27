import numpy as np
from sim.pitnn.hodgkin_huxley_ciss import FHNConfig, ciss_torque, cytosolic_field, simulate_fhn, stark_shift

def test_fhn_field_stark_and_torque_are_finite():
    times, voltage, _ = simulate_fhn(FHNConfig(duration_s=1e-3, dt_s=1e-5))
    field = cytosolic_field(voltage); shifts = stark_shift(np.tile([1e-29, 0, 0], (len(field), 1)), field)
    torque = ciss_torque(1.0, 1e-7, field)
    assert len(times) == len(voltage) and np.ptp(voltage) > .09
    assert np.all(np.isfinite(field)) and np.all(np.isfinite(shifts)) and np.all(torque >= 1)
