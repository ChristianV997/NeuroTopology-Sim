
def winding_metrics(charges: list[int]) -> dict[str, float]:
    q_net = float(sum(charges))
    q_abs = float(sum(abs(q) for q in charges))
    q_excess = q_abs - abs(q_net)
    f_dress = q_excess / q_abs if q_abs else 0.0
    return {"q_net": q_net, "q_abs": q_abs, "q_excess": q_excess, "f_dress": f_dress}


def smooth_field_fixture() -> list[int]:
    return []


def single_vortex_fixture() -> list[int]:
    return [1]


def antivortex_fixture() -> list[int]:
    return [-1]


def vortex_antivortex_pair_fixture() -> list[int]:
    return [1, -1]


def random_phase_foam_fixture() -> list[int]:
    return [1, -1, 1, -1, 1, -1, 1, -1, 1, -1]
