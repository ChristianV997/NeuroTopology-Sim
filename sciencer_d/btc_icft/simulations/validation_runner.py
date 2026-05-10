import json
from pathlib import Path

from sciencer_d.btc_icft.omega.firewall import omega_firewall
from sciencer_d.btc_icft.simulations.synthetic_d import reactive_trajectory, trained_trajectory
from sciencer_d.btc_icft.simulations.synthetic_t import synthetic_winding_summary


def run_synthetic_validation(out_dir: str) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    rb, rr = reactive_trajectory()
    tb, tr = trained_trajectory()
    winding = synthetic_winding_summary()

    metrics = {
        "reactive_delta_d_lock": rr - rb,
        "trained_delta_d_lock": tr - tb,
        "random_phase_foam_promotion_safe": winding["q_net"] != 0 and winding["q_abs"] <= 2,
    }

    omega_ok, omega_msg = omega_firewall("telemetry: residual predictive value improves")
    omega_event = {"accepted": omega_ok, "message": omega_msg}

    (out / "synthetic_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (out / "omega_event.json").write_text(json.dumps(omega_event, indent=2), encoding="utf-8")
    (out / "report.md").write_text(
        "# BTC/ICFT Synthetic Validation\n"
        f"- Reactive delta D_lock: {metrics['reactive_delta_d_lock']:.3f}\n"
        f"- Trained delta D_lock: {metrics['trained_delta_d_lock']:.3f}\n"
        f"- Random phase foam promotion safe: {metrics['random_phase_foam_promotion_safe']}\n",
        encoding="utf-8",
    )
    return {"metrics": metrics, "omega_event": omega_event}
