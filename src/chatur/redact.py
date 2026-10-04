"""Secret masking for anything persisted (ADR-0006, ADR-0015). Stdlib-only (ADR-0012).

Masked values become ``[REDACTED:<kind>]``. Patterns favour catching secrets over keeping text;
every pattern has positive and false-positive tests.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from functools import lru_cache
from typing import Any

# (kind, pattern). Order matters: specific token formats before generic credential shapes.
_TOKEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private_key",
        re.compile(
            r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"
            r".*?-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----",
            re.DOTALL,
        ),
    ),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("openai_key", re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_\-]{20,}")),
    ("github_token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("slack_token", re.compile(r"\bxox[abposr]-[A-Za-z0-9\-]{10,}")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("stripe_key", re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}")),
)

_CRED_WORDS = (  # words that label a credential value
    r"pass(?:word|wd)?|pwd|secret|token|api[_-]?key|apikey|access[_-]?key|auth(?!or)|credentials?"
    r"|client[_-]?secret|private[_-]?key"
)

# Value character classes exclude "[" and "]" so an already-inserted mask is never re-matched.
_VALUE = r"[^\s'\"&;|\[\]]{3,}"

# Credential shapes: keep the label, mask the value.
_SHAPE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # https://user:pass@host
    (
        "url_credentials",
        re.compile(r"(?P<keep>[a-z][a-z0-9+.\-]*://[^\s:/@\[\]]+:)[^\s@/\[\]]+(?=@)", re.I),
    ),
    # Authorization: Bearer xxx / Basic xxx
    (
        "auth_header",
        re.compile(r"(?P<keep>\b(?:Bearer|Basic|Token)\s+)[A-Za-z0-9._~+/=\-]{8,}", re.I),
    ),
    # password=xxx, API_KEY: "xxx", $env:TOKEN = 'xxx'
    (
        "credential",
        re.compile(
            rf"(?P<keep>\b[\w.\-]*(?:{_CRED_WORDS})[\w.\-]*['\"]?\s*[:=]\s*['\"]?){_VALUE}",
            re.I,
        ),
    ),
    # --password xxx, --token=xxx style flags
    (
        "credential_flag",
        re.compile(rf"(?P<keep>--?(?:{_CRED_WORDS})[\w\-]*[\s=:]+['\"]?){_VALUE}", re.I),
    ),
)

_SENSITIVE_KEY = re.compile(rf"(?:^|[_\-.])(?:{_CRED_WORDS})(?:$|[_\-.])", re.I)


def _mask(kind: str) -> str:
    return f"[REDACTED:{kind}]"


@lru_cache(maxsize=256)
def _custom(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern)


def redact_text(text: str, extra: Sequence[str] = ()) -> str:
    """Mask secrets. `extra` = project regexes from policy.local.toml [redact] (ADR-0015)."""
    for pattern in extra:
        text = _custom(pattern).sub(_mask("custom"), text)
    for kind, pattern in _TOKEN_PATTERNS:
        text = pattern.sub(_mask(kind), text)
    for kind, pattern in _SHAPE_PATTERNS:
        text = pattern.sub(lambda m, k=kind: m.group("keep") + _mask(k), text)
    return text


def is_sensitive_key(key: str) -> bool:
    return bool(_SENSITIVE_KEY.search(key))


def redact(value: Any, extra: Sequence[str] = ()) -> Any:
    """Recursively mask secrets in strings, and all values stored under sensitive keys."""
    if isinstance(value, str):
        return redact_text(value, extra)
    if isinstance(value, Mapping):
        out: dict[Any, Any] = {}
        for k, v in value.items():
            if isinstance(k, str) and is_sensitive_key(k) and isinstance(v, str | int | float):
                out[k] = _mask("sensitive_key")
            else:
                out[k] = redact(v, extra)
        return out
    if isinstance(value, list | tuple):
        return type(value)(redact(v, extra) for v in value)
    return value
