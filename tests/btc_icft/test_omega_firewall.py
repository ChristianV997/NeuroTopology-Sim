from sciencer_d.btc_icft.omega.firewall import omega_firewall


def test_omega_rejects_overclaim():
    ok, _ = omega_firewall("This proves consciousness as ultimate reality")
    assert not ok
