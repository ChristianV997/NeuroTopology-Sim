from sciencer_d.btc_icft.labels.contracts import validate_label_contract


def test_blocked_shortcuts():
    assert not validate_label_contract("unresponsive", "no_experience")
    assert not validate_label_contract("unresponsive", "unconscious")
    assert not validate_label_contract("cessation_candidate", "liberation")
    assert not validate_label_contract("meditation", "attainment")
