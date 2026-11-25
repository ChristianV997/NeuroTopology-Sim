"""Command-line entry point: ``python -m shared.measurement_hypothesis MAPPING.json``."""
from __future__ import annotations

from .validate import main

raise SystemExit(main())
