from sciencer_d.btc_icft.level_t.winding import random_phase_foam_fixture, winding_metrics


def synthetic_winding_summary() -> dict[str, float]:
    return winding_metrics(random_phase_foam_fixture())
