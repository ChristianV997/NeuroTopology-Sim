BANNED_PATTERNS = {
    "ultimate reality",
    "proves consciousness",
    "consciousness proven",
    "metaphysical truth",
    "ontology solved",
    "consciousness ontology solved",
    "liberation detected",
    "attainment detected",
    "proves liberation",
    "proves enlightenment",
    "unconsciousness proven",
    "afterlife proven",
    "soul proven",
    "q equals self",
    "q equals soul",
    "q_abs equals suffering",
    "f_dress equals karma",
    "entropy equals dukkha",
    "high lzc proves awakening",
    "microtubules prove consciousness",
    "qed proves consciousness",
    "rg fixed point is nibbana",
    "rg fixed point is nibbāna",
    "qec proves self",
    "cessation proves liberation",
    "nde proves afterlife",
    "theravada realms are proven",
    "multiverse proves the realms",
}

APPROVED_CAUTIOUS_FRAMES = {
    "telemetry",
    "proxy",
    "mechanism hypothesis",
    "residual predictive value",
    "synthetic scaffold",
    "operational marker",
    "candidate metric",
    "evidence ledger",
}


def omega_firewall(claim: str) -> tuple[bool, str]:
    text = claim.lower()
    if any(pattern in text for pattern in BANNED_PATTERNS):
        return False, "rejected: ontology/metaphysical overclaim"
    if not any(frame in text for frame in APPROVED_CAUTIOUS_FRAMES):
        return False, "rejected: claim must use approved cautious framing"
    return True, "accepted: cautious scientific framing"


def frame_claim(claim: str) -> tuple[bool, str]:
    return omega_firewall(claim)
