BLOCKED_SHORTCUTS = {
    ("unresponsive", "no_experience"),
    ("unresponsive", "unconscious"),
    ("cessation_candidate", "liberation"),
    ("meditation", "attainment"),
}


def validate_label_contract(observed_label: str, shortcut_label: str) -> bool:
    """Return True when a shortcut assertion is allowed by policy."""
    return (observed_label, shortcut_label) not in BLOCKED_SHORTCUTS
