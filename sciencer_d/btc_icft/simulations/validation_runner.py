import json
from pathlib import Path

from sciencer_d.btc_icft.omega.firewall import omega_firewall
from sciencer_d.btc_icft.simulations.synthetic_d import reactive_trajectory, trained_trajectory
from sciencer_d.btc_icft.simulations.synthetic_t import synthetic_winding_summary


REPORT_BANNED_PHRASES = {
    "proves consciousness",
    "soul proven",
    "afterlife proven",
    "liberation detected",
    "ontology solved",
    "ultimate reality",
    "q equals self",
    "q equals soul",
    "q_abs equals suffering",
    "f_dress equals karma",
}


def run_synthetic_validation(out_dir: str) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    rb, rr = reactive_trajectory()
    tb, tr = trained_trajectory()
    winding = synthetic_winding_summary()

    random_phase_foam_blocked = winding["q_net"] == 0 or winding["q_abs"] > 2
    random_phase_foam_block_reason = "high_q_abs_zero_net_foam" if random_phase_foam_blocked else ""
    metrics = {
        "reactive_delta_d_lock": rr - rb,
        "trained_delta_d_lock": tr - tb,
        "random_phase_foam_promotion_safe": not random_phase_foam_blocked,
        "random_phase_foam_blocked": random_phase_foam_blocked,
        "random_phase_foam_block_reason": random_phase_foam_block_reason,
        "random_phase_foam_q_net": winding["q_net"],
        "random_phase_foam_q_abs": winding["q_abs"],
        "random_phase_foam_f_dress": winding["f_dress"],
    }

    omega_ok, omega_msg = omega_firewall("telemetry proxy for residual predictive value in synthetic scaffold")
    omega_event = {"accepted": omega_ok, "message": omega_msg}

    report = (
        "# BTC/ICFT Synthetic Validation\n"
        "This deterministic fixture is a synthetic scaffold for telemetry and proxy evaluation.\n"
        "Residual gate context is included as an operational proxy only.\n"
        f"- Reactive delta D_lock: {metrics['reactive_delta_d_lock']:.3f}\n"
        f"- Trained delta D_lock: {metrics['trained_delta_d_lock']:.3f}\n"
        f"- Random phase foam promotion safe: {metrics['random_phase_foam_promotion_safe']}\n"
        f"- Random phase foam blocked: {metrics['random_phase_foam_blocked']} ({metrics['random_phase_foam_block_reason']})\n"
    )
    for phrase in REPORT_BANNED_PHRASES:
        assert phrase not in report.lower()

    (out / "synthetic_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (out / "omega_event.json").write_text(json.dumps(omega_event, indent=2), encoding="utf-8")
    (out / "report.md").write_text(report, encoding="utf-8")
    return {"metrics": metrics, "omega_event": omega_event}
