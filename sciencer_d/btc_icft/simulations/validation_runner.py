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


def _foam_block_reason(q_net: int | float, q_abs: int | float) -> tuple[bool, str]:
    blocked = q_net == 0 or q_abs > 2
    if not blocked:
        return False, ""
    if q_net == 0 and q_abs > 2:
        return True, "zero_net_high_q_abs_foam"
    if q_net == 0:
        return True, "zero_net_foam"
    return True, "high_q_abs_foam"


def _validate_report_safety(report: str) -> None:
    report_lower = report.lower()
    for phrase in REPORT_BANNED_PHRASES:
        if phrase in report_lower:
            raise ValueError(f"Unsafe report phrase detected: {phrase}")


def run_synthetic_validation(out_dir: str) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    rb, rr = reactive_trajectory()
    tb, tr = trained_trajectory()
    winding = synthetic_winding_summary()

    random_phase_foam_blocked, random_phase_foam_block_reason = _foam_block_reason(
        winding["q_net"],
        winding["q_abs"],
    )
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
    _validate_report_safety(report)

    (out / "synthetic_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (out / "omega_event.json").write_text(json.dumps(omega_event, indent=2), encoding="utf-8")
    (out / "report.md").write_text(report, encoding="utf-8")
    return {"metrics": metrics, "omega_event": omega_event}
