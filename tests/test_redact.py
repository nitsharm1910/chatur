"""Secret masking (ADR-0015): every pattern has a positive and a false-positive test."""

import pytest

from chatur.redact import is_sensitive_key, redact, redact_text

# Built at runtime so this file never contains a contiguous secret-shaped literal.
FAKE = {
    "anthropic_key": "sk-ant-" + "api03-" + "A" * 40,
    "openai_key": "sk-" + "proj-" + "b" * 40,
    "github_token": "ghp_" + "c" * 36,
    "aws_access_key": "AKIA" + "ABCDEFGHIJKLMNOP",
    "slack_token": "xoxb-" + "1234567890-abcdef",
    "google_api_key": "AIza" + "D" * 35,
    "stripe_key": "sk_" + "live_" + "e" * 24,
    "jwt": "eyJ" + "hbGciOiJIUzI1" + "." + "eyJ" + "zdWIiOiIxMjM0" + "." + "f" * 20,
}


@pytest.mark.parametrize(("kind", "secret"), FAKE.items())
def test_token_formats_masked(kind, secret):
    out = redact_text(f"curl -H x {secret} https://example.com")
    assert secret not in out
    assert f"[REDACTED:{kind}]" in out


def test_private_key_block_masked():
    kind = "RSA " + "PRIVATE KEY"  # built at runtime: no literal key block in the repo (ADR-0030)
    pem = f"-----BEGIN {kind}-----\nMIIEow\nabc\n-----END {kind}-----"
    out = redact_text(f"echo '{pem}' > id_rsa")
    assert "MIIEow" not in out
    assert "[REDACTED:private_key]" in out


@pytest.mark.parametrize(
    ("text", "leaked"),
    [
        ("export API_KEY=abc123xyz", "abc123xyz"),
        ("$env:GITHUB_TOKEN = 'tok_value_99'", "tok_value_99"),
        ('{"password": "hunter2!"}', "hunter2!"),
        ("mysql --password=s3cr3tpw -u root", "s3cr3tpw"),
        ("login --token abcdef123456", "abcdef123456"),
        ("curl -H 'Authorization: Bearer abc.def.ghi123'", "abc.def.ghi123"),
        ("git clone https://nitin:pa55word@github.com/x/y.git", "pa55word"),
        ("DB_PASSWD=letmein123 ./run", "letmein123"),
    ],
)
def test_credential_shapes_masked_and_label_kept(text, leaked):
    out = redact_text(text)
    assert leaked not in out
    assert "[REDACTED:" in out


@pytest.mark.parametrize(
    "text",
    [
        "git status",
        "git log --oneline -5",
        'git commit --author="Nitin <n@example.com>" -m "fix"',
        "python -m pytest tests/test_redact.py",
        r"Get-ChildItem C:\Users\nitin\Chatur\src",
        "ls -la /home/user/projects/tokenizer",
        "npm install --save-dev typescript",
        "cat docs/decisions/0015-audit-full-commands-masked.md",
        "echo password reset flow docs",
    ],
)
def test_ordinary_commands_untouched(text):
    assert redact_text(text) == text


def test_sensitive_keys_in_structures():
    data = {
        "toolArgs": {"api_key": "x1", "client_secret": "y2", "path": "a.txt"},
        "env": [{"GITHUB_TOKEN": "z3"}],
        "author": "Nitin",
        "tokens_used": 42,
    }
    out = redact(data)
    assert out["toolArgs"]["api_key"] == "[REDACTED:sensitive_key]"
    assert out["toolArgs"]["client_secret"] == "[REDACTED:sensitive_key]"
    assert out["toolArgs"]["path"] == "a.txt"
    assert out["env"][0]["GITHUB_TOKEN"] == "[REDACTED:sensitive_key]"
    assert out["author"] == "Nitin"
    assert out["tokens_used"] == 42


@pytest.mark.parametrize(
    "key", ["password", "API_KEY", "x-auth-token", "aws.secret", "credentials"]
)
def test_is_sensitive_key_positive(key):
    assert is_sensitive_key(key)


@pytest.mark.parametrize("key", ["author", "path", "tokens_used", "command", "passage"])
def test_is_sensitive_key_negative(key):
    assert not is_sensitive_key(key)


@pytest.mark.parametrize("secret", FAKE.values())
def test_masks_are_never_re_masked(secret):
    # Regression: url_credentials used to re-match inside an inserted mask.
    out = redact_text(f"git clone https://{secret}@github.com/a/b && export TOKEN={secret}")
    assert "[REDACTED:[" not in out
    assert redact_text(out) == out  # idempotent


@pytest.mark.parametrize(
    "line",
    [
        '"event": strip_file_contents(event.to_dict(redact_secrets=False)),',
        '"""Normalised path vs glob: ancestor and wildcard-token rules (ADR-0017)."""',
        "A shell token containing wildcards matches if it",
        '1. **New selector `contains_secret = "token" | "credential" | "any"`**',
        'TOKEN = "ghp_" + "Q7dLm2xP9vR4kT8wZ1bN6cY3hJ5fS0gAeUoI"',
        "token = config.apiKey",
        "secret = getenv(",
        "token = _glob_regex(path)",
        "secrets=_secret_findings(event, shell)",
        '_SECRET_LEVELS = frozenset({"token", "credential", "any"})',
    ],
)
def test_prose_and_code_are_not_credentials(line):
    # Regressions from running ci-check on Chatur itself (2026-10-12).
    from chatur.redact import find_secrets

    assert [f for f in find_secrets(line) if f.category == "credential"] == []


@pytest.mark.parametrize(
    "line",
    [
        "export API_KEY=abc123xyz",
        "mysql --password=s3cr3tpw -u root",
        "curl -H 'Authorization: Bearer abc.def.ghi123'",
        "curl -H 'Authorization: token ab12cd34ef56'",
        'DB_PASSWORD = "s3cr3t-Value9"',
        "git clone https://nitin:pa55word@github.com/x/y.git",
    ],
)
def test_real_credential_shapes_still_detected(line):
    from chatur.redact import find_secrets

    assert any(f.category == "credential" for f in find_secrets(line))


def test_redact_does_not_mutate_input():
    data = {"password": "p", "nested": ["export TOKEN=abcdef"]}
    redact(data)
    assert data == {"password": "p", "nested": ["export TOKEN=abcdef"]}
