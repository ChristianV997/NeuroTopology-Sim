"""Stage locks for manifest/hash-gated research execution."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import secrets
from typing import Any


class StagePolicyError(ValueError):
    """Raised when a locked-stage policy is violated."""


@dataclass
class StageLock:
    stage: str
    protocol_hash: str
    issued_for: str
    token: str
    consumed: bool = False
    consumed_at: str | None = None

    @classmethod
    def issue(cls, stage: str, protocol_hash: str, issued_for: str) -> "StageLock":
        if stage not in {"confirmatory", "external"}:
            raise StagePolicyError("only confirmatory and external stages can be locked")
        if not protocol_hash or not issued_for:
            raise StagePolicyError("lock requires protocol hash and issued_for identifier")
        return cls(stage, protocol_hash, issued_for, secrets.token_hex(16))

    def consume(self, protocol_hash: str, issued_for: str) -> None:
        if self.consumed:
            raise StagePolicyError(f"{self.stage} lock has already been consumed")
        if protocol_hash != self.protocol_hash:
            raise StagePolicyError("protocol hash does not match the stage lock")
        if issued_for != self.issued_for:
            raise StagePolicyError("stage lock was issued for a different run")
        self.consumed = True
        self.consumed_at = datetime.now(timezone.utc).isoformat()

    def authorize(self, protocol_hash: str, issued_for: str) -> None:
        if self.consumed:
            raise StagePolicyError(f"{self.stage} lock has already been consumed")
        if protocol_hash != self.protocol_hash or issued_for != self.issued_for:
            raise StagePolicyError("stage lock authorization failed")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
