"""Speculative theoretical exploration track -- segregated by design.

Everything under `sim/speculative/` explores physics-inspired constructs
(stochastic Langevin-lattice field dynamics, non-Hermitian effective-
Hamiltonian cross-checks) that are NOT established neuroscience findings.
This package is intentionally, technically decoupled from the real-EEG
analysis pipeline (`sciencer_d/btc_icft/`) and from every published dataset
report: it must never be imported by, and its output must never feed into,
either. `tests/test_speculative_boundary.py` enforces this with a static
import-graph check, not just a naming convention.

`SPECULATIVE_BANNER` must appear verbatim in every report/markdown artifact
this package produces; `validate_speculative_text` enforces both the banner
and a banned-overclaiming-phrase list, checked with `validate_speculative_text`
before any speculative output is written or returned.

The banned-phrase list below is intentionally a literal duplicate of
`sciencer_d/btc_icft/report_guardrails.py::BANNED_REPORT_PHRASES`, not an
import of it -- keeping this package's import graph fully disjoint from
`sciencer_d.btc_icft` (see above). If the canonical list changes, this copy
must be updated by hand; `tests/test_speculative_boundary.py` includes a
drift check that fails loudly if the two lists diverge, so this is a
detected manual-sync obligation, not a silent risk.
"""
from __future__ import annotations

SPECULATIVE_BANNER = (
    "SPECULATIVE THEORETICAL EXPLORATION -- NOT A VALIDATED SCIENTIFIC "
    "FINDING, NOT A CLAIM ABOUT BIOLOGICAL CONSCIOUSNESS."
)

# Deliberately duplicated, not imported -- see module docstring above.
BANNED_REPORT_PHRASES: tuple[str, ...] = (
    "proves consciousness",
    "soul proven",
    "afterlife proven",
    "liberation detected",
    "enlightenment proven",
    "nirvana confirmed",
    "ontology solved",
    "ultimate reality",
    "q equals self",
    "q equals soul",
    "q_abs equals suffering",
    "f_dress equals karma",
)


def validate_speculative_text(text: str) -> None:
    """Raise ValueError if `text` lacks the required `SPECULATIVE_BANNER`
    or contains any banned overclaiming phrase (case-insensitive)."""
    if SPECULATIVE_BANNER not in text:
        raise ValueError("speculative output missing required SPECULATIVE_BANNER")
    low = text.lower()
    for phrase in BANNED_REPORT_PHRASES:
        if phrase in low:
            raise ValueError(f"banned phrase detected in speculative output: {phrase}")
