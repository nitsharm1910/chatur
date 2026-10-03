"""Guard verdicts. The strictest matching rule wins (ADR-0007, ADR-0014). Stdlib-only (ADR-0012)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Decision(StrEnum):
    ALLOW = "allow"
    LOG = "log"
    WARN = "warn"
    ASK = "ask"
    DENY = "deny"

    @property
    def severity(self) -> int:
        return _SEVERITY[self]

    @property
    def blocks(self) -> bool:
        """True when the action must not proceed without (or despite) a human."""
        return self in (Decision.ASK, Decision.DENY)


_SEVERITY = {
    Decision.ALLOW: 0,
    Decision.LOG: 1,
    Decision.WARN: 2,
    Decision.ASK: 3,
    Decision.DENY: 4,
}


def strictest(decisions: Iterable[Decision]) -> Decision:
    return max(decisions, key=lambda d: d.severity, default=Decision.ALLOW)


@dataclass(frozen=True, slots=True)
class RuleHit:
    """One rule that matched an event."""

    rule_id: str
    decision: Decision
    reason: str
    adr: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "decision": self.decision.value,
            "reason": self.reason,
            "adr": self.adr,
        }


@dataclass(frozen=True, slots=True)
class Verdict:
    decision: Decision
    reason: str
    hits: tuple[RuleHit, ...] = ()
    profile: str | None = None

    @classmethod
    def from_hits(
        cls,
        hits: Iterable[RuleHit],
        *,
        default: Decision = Decision.ALLOW,
        profile: str | None = None,
    ) -> Verdict:
        """Combine matching rules: strictest decision wins; reasons at that level are joined."""
        hits = tuple(hits)
        if not hits:
            return cls(decision=default, reason="no rule matched", profile=profile)
        decision = strictest(h.decision for h in hits)
        reason = "; ".join(f"[{h.rule_id}] {h.reason}" for h in hits if h.decision is decision)
        return cls(decision=decision, reason=reason, hits=hits, profile=profile)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "reason": self.reason,
            "hits": [h.to_dict() for h in self.hits],
            "profile": self.profile,
        }
