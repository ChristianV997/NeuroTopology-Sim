"""Single source of truth for the report-safety phrase guard.

Previously `BANNED_REPORT_PHRASES` and `_validate_safe_text` were copy-pasted
verbatim across 9 files (`datasets/ds005620.py`,
`evaluation/ds005620_residual.py`, `level_m/{ds005620,ds003969,ds001787}_windows.py`,
`level_t/{ds005620_features,ds005620_real_topology,ds003969_real_topology,
ds001787_real_topology}.py`). The copy had already drifted once: the two files
touched by the ds003969/ds001787 meditation ports added "enlightenment proven"
and "nirvana confirmed" (meditation-specific overclaiming risk) but that
addition was never backported to the 5 older ds005620-lineage copies -- so the
guard was silently weaker on more than half the files it existed in. All 9
files now import from here instead of declaring their own copy.
"""
from __future__ import annotations

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


def validate_safe_text(text: str, extra_banned_phrases: tuple[str, ...] = ()) -> None:
    """Raise ValueError if `text` contains any banned phrase (case-insensitive).

    `extra_banned_phrases` lets a caller add dataset-specific phrases on top of
    the shared base list without needing its own copy of the base list.
    """
    low = text.lower()
    for phrase in BANNED_REPORT_PHRASES + tuple(extra_banned_phrases):
        if phrase in low:
            raise ValueError(f"banned phrase detected: {phrase}")
