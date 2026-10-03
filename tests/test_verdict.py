"""Verdict combination: strictest rule wins (ADR-0007, ADR-0014)."""

import pytest

from chatur.verdict import Decision, RuleHit, Verdict, strictest


def test_severity_order():
    order = [Decision.ALLOW, Decision.LOG, Decision.WARN, Decision.ASK, Decision.DENY]
    assert sorted(reversed(order), key=lambda d: d.severity) == order


@pytest.mark.parametrize(
    ("decisions", "expected"),
    [
        ([], Decision.ALLOW),
        ([Decision.LOG, Decision.WARN], Decision.WARN),
        ([Decision.ASK, Decision.DENY, Decision.ALLOW], Decision.DENY),
        ([Decision.ASK, Decision.WARN], Decision.ASK),
    ],
)
def test_strictest(decisions, expected):
    assert strictest(decisions) is expected


def test_blocks():
    assert Decision.DENY.blocks and Decision.ASK.blocks
    assert not Decision.WARN.blocks


def test_no_hits_uses_default():
    v = Verdict.from_hits([], default=Decision.ASK, profile="standard")
    assert v.decision is Decision.ASK
    assert v.profile == "standard"


def test_deny_beats_ask_and_reasons_come_from_winning_level():
    hits = [
        RuleHit("exec.needs-approval", Decision.ASK, "needs approval", "ADR-0014"),
        RuleHit("git.no-commit-push", Decision.DENY, "no commit", "ADR-0014"),
    ]
    v = Verdict.from_hits(hits)
    assert v.decision is Decision.DENY
    assert v.reason == "[git.no-commit-push] no commit"
    assert len(v.hits) == 2  # all hits retained for the audit log


def test_to_dict():
    v = Verdict.from_hits([RuleHit("r1", Decision.WARN, "w")], profile="relaxed")
    assert v.to_dict() == {
        "decision": "warn",
        "reason": "[r1] w",
        "hits": [{"rule_id": "r1", "decision": "warn", "reason": "w", "adr": None}],
        "profile": "relaxed",
    }
