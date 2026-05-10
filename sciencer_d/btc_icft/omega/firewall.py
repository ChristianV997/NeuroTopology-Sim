BANNED_TERMS = {"ultimate reality", "proves consciousness", "metaphysical truth", "ontology"}
ALLOWED_FRAMES = {"telemetry", "proxy", "mechanism hypothesis", "residual predictive value"}


def omega_firewall(claim: str) -> tuple[bool, str]:
    text = claim.lower()
    if any(term in text for term in BANNED_TERMS):
        return False, "rejected: ontology/metaphysical overclaim"
    if not any(frame in text for frame in ALLOWED_FRAMES):
        return False, "rejected: claim must use approved framing"
    return True, "accepted"
