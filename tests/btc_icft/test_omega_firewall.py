from sciencer_d.btc_icft.omega.firewall import omega_firewall


def test_omega_accepts_cautious_claims():
    for claim in [
        "telemetry proxy for residual predictive value",
        "candidate metric for synthetic scaffold",
    ]:
        ok, reason = omega_firewall(claim)
        assert ok
        assert reason == "accepted: cautious scientific framing"


def test_omega_rejects_no_frame_claim():
    ok, reason = omega_firewall("this metric is interesting")
    assert not ok
    assert reason == "rejected: claim must use approved cautious framing"


def test_omega_rejects_banned_claims():
    banned_claims = [
        "Q equals self",
        "Q equals soul",
        "Q_abs equals suffering",
        "f_dress equals karma",
        "entropy equals dukkha",
        "high LZC proves awakening",
        "microtubules prove consciousness",
        "QED proves consciousness",
        "RG fixed point is nibbana",
        "RG fixed point is nibbāna",
        "QEC proves self",
        "cessation proves liberation",
        "NDE proves afterlife",
        "consciousness ontology solved",
    ]
    for claim in banned_claims:
        ok, reason = omega_firewall(claim)
        assert not ok
        assert reason == "rejected: ontology/metaphysical overclaim"


def test_omega_rejects_mixed_overclaims_before_frame_acceptance():
    mixed_claims = [
        "telemetry proxy proves consciousness as ultimate reality",
        "residual predictive value shows soul proven",
        "mechanism hypothesis: RG fixed point is nibbana",
    ]
    for claim in mixed_claims:
        ok, reason = omega_firewall(claim)
        assert not ok
        assert reason == "rejected: ontology/metaphysical overclaim"
