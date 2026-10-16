#!/usr/bin/env python
"""Run the Batch 3 offline integration fixture harness.

Thin wrapper around ``python -m tools.batch3_offline_integration``.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tools.batch3_offline_integration.__main__ import main


if __name__ == "__main__":
    raise SystemExit(main())
