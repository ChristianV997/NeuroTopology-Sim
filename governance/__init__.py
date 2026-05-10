"""Governance harness for Awareness Research v0.2."""

from governance.io import load_spec, save_spec
from governance.spec import HypothesisSpec

__all__ = ["HypothesisSpec", "validate_spec", "ValidationError", "load_spec", "save_spec"]


def __getattr__(name: str):
    if name in {"validate_spec", "ValidationError"}:
        from governance.validate import ValidationError, validate_spec

        return {"validate_spec": validate_spec, "ValidationError": ValidationError}[name]
    raise AttributeError(f"module 'governance' has no attribute {name!r}")
