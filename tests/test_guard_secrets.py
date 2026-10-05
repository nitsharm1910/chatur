"""Secret detection rules (ADR-0007, ADR-0023): tiered, all scan locations, placeholders ignored."""

import base64

import pytest

from chatur.events import ChaturEvent, EventKind, ToolCall, ToolCategory
from chatur.redact import find_secrets, is_placeholder
from chatur.verdict import Decision
from conftest import ROOT, check, hit_ids, shell_event, write_event

VARIED = "Q7dLm2xP9vR4kT8wZ1bN6cY3hJ5fS0gAeUoIqWtE"  # high-variety body, built at runtime


def fake(prefix: str, n: int, alphabet: str = VARIED) -> str:
    return prefix + (alphabet * 3)[:n]


GH = fake("ghp_", 36)
AWS = fake("AKIA", 16, "Q7DLM2XP9VR4KT8WZ1BN6CY3")
ANTHROPIC = fake("sk-ant-api03-", 40)
OPENAI = fake("sk-proj-", 40)
SLACK = fake("xoxb-", 24)
GOOGLE = fake("AIza", 35)
STRIPE = fake("sk_" + "live_", 24)
PEM = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA7d\n-----END RSA PRIVATE KEY-----"


def tool(category: ToolCategory, name: str, args: dict, *, attended: bool = True) -> ChaturEvent:
    return ChaturEvent(
        kind=EventKind.PRE_TOOL,
        assistant="test",
        session_id="s",
        cwd=ROOT,
        attended=attended,
        tool=ToolCall(
            category, name, args, paths=tuple(v for k, v in args.items() if k == "file_path")
        ),
    )


def prompt(text: str) -> ChaturEvent:
    return ChaturEvent(
        kind=EventKind.PROMPT, assistant="test", session_id="s", cwd=ROOT, prompt=text
    )


def _enc(command: str) -> str:
    return base64.b64encode(command.encode("utf-16-le")).decode()


# --------------------------------------------------------------------------- deny: known tokens

DENY = {
    "write-py": write_event("config.py", f'TOKEN = "{GH}"'),
    "write-env-aws": write_event(".env", f"AWS_ACCESS_KEY_ID={AWS}\n"),
    "write-pem": write_event("id_rsa", PEM),
    "edit-new-string": tool(
        ToolCategory.FILE_WRITE,
        "Edit",
        {"file_path": "a.py", "old_string": "x = 1", "new_string": f"KEY = '{ANTHROPIC}'"},
    ),
    "shell-bearer": shell_event(f"curl -H 'Authorization: Bearer {GH}' https://api.github.com"),
    "shell-nested": shell_event(f'sh -c "export OPENAI_API_KEY={OPENAI}"'),
    "shell-encoded": shell_event(
        f"pwsh -EncodedCommand {_enc('$env:K=' + chr(39) + STRIPE + chr(39))}"
    ),
    "mcp-args": tool(ToolCategory.MCP, "mcp__slack__post", {"text": f"token is {SLACK}"}),
    "web-url": tool(
        ToolCategory.WEB, "WebFetch", {"url": f"https://maps.example/api?key={GOOGLE}"}
    ),
    "agent-prompt": tool(ToolCategory.AGENT, "Task", {"prompt": f"deploy with {STRIPE}"}),
    "nested-args": tool(ToolCategory.MCP, "mcp__x__y", {"payload": {"items": [{"v": GH}]}}),
}


@pytest.mark.parametrize("name", sorted(DENY))
def test_known_tokens_denied(name):
    verdict = check(DENY[name])
    assert verdict.decision is Decision.DENY, f"{name}: {verdict.reason}"
    assert "secrets.known-token" in hit_ids(verdict)


@pytest.mark.parametrize("profile", ["strict", "standard", "relaxed"])
def test_token_denied_in_every_profile(profile):
    assert check(DENY["write-py"], profile).decision is Decision.DENY


# --------------------------------------------------------------------------- ask: credential shapes


@pytest.mark.parametrize(
    "event",
    [
        write_event("settings.py", 'DB_PASSWORD = "s3cr3t-Value9"'),
        shell_event("mysql --password=Hunter2Pass -u root"),
        tool(ToolCategory.MCP, "mcp__db__connect", {"dsn": "postgres://app:Pa55-w0rdX@db/prod"}),
    ],
    ids=["write", "shell", "mcp"],
)
def test_credential_shapes_ask(event):
    verdict = check(event)
    assert verdict.decision is Decision.ASK, verdict.reason
    assert "secrets.credential-shape" in hit_ids(verdict)
    assert "secrets.known-token" not in hit_ids(verdict)


def test_credential_shape_unattended_denied():
    event = write_event("settings.py", 'DB_PASSWORD = "s3cr3t-Value9"', attended=False)
    assert check(event).decision is Decision.DENY


# --------------------------------------------------------------------------- not flagged


@pytest.mark.parametrize(
    "event",
    [
        tool(
            ToolCategory.FILE_WRITE,
            "Edit",
            {
                "file_path": "a.py",
                "old_string": f"TOKEN = '{GH}'",
                "new_string": "TOKEN = os.environ['GITHUB_TOKEN']",
            },
        ),
        write_event("a.py", 'TOKEN = "${GITHUB_TOKEN}"'),
        write_event("a.yml", "api_key: <your-api-key>"),
        write_event("a.ini", "password=changeme"),
        write_event("docs.md", "Example key: AKIAIOSFODNN7EXAMPLE"),
        write_event("fixture.py", "TOKEN = 'ghp_" + "x" * 36 + "'"),
        write_event("cfg.yml", "password: $DB_PASSWORD"),
        write_event("a.js", "const token = process.env.GITHUB_TOKEN;"),
        write_event("a.py", "password = os.getenv('DB_PASSWORD')"),
        write_event("a.ts", "apiKey: config.apiKey,"),
        shell_event("curl -H 'Authorization: Bearer $GITHUB_TOKEN' https://api.github.com"),
        write_event("app.py", "def login(user, password):\n    return check(user, password)\n"),
        tool(ToolCategory.FILE_READ, "Read", {"file_path": ".env"}),
    ],
    ids=[
        "removing-secret",
        "env-ref",
        "angle-placeholder",
        "changeme",
        "aws-doc-example",
        "low-variety",
        "shell-var",
        "js-process-env",
        "py-getenv",
        "ts-config-ref",
        "bearer-var",
        "normal-code",
        "file-read",
    ],
)
def test_not_flagged(event):
    hits = hit_ids(check(event))
    assert not {h for h in hits if h.startswith("secrets.")}, hits


# --------------------------------------------------------------------------- prompts


def test_prompt_with_token_warns():
    verdict = check(prompt(f"here is my token {GH}, please use it"))
    assert verdict.decision is Decision.WARN
    assert "secrets.in-prompt" in hit_ids(verdict)


def test_prompt_with_credential_warns():
    assert check(prompt("the db password=Hunter2Pass")).decision is Decision.WARN


def test_plain_prompt_allowed():
    assert check(prompt("please refactor the login module")).decision is Decision.ALLOW


# --------------------------------------------------------------------------- helpers


@pytest.mark.parametrize(
    "value",
    [
        "${TOKEN}",
        "<token>",
        "changeme",
        "CHANGE_ME",
        "AKIAIOSFODNN7EXAMPLE",
        "ghp_" + "x" * 36,
        "$DB_PASSWORD",
        "$env:API_KEY",
        "%API_KEY%",
        "your-key-here",
        "[REDACTED:x]",
        "{{ secret }}",
    ],
)
def test_is_placeholder(value):
    assert is_placeholder(value)


@pytest.mark.parametrize("value", [GH, AWS, "s3cr3t-Value9", "Hunter2Pass"])
def test_real_values_not_placeholder(value):
    assert not is_placeholder(value)


def test_find_secrets_categories():
    found = find_secrets(f"export GITHUB_TOKEN={GH}")
    assert {f.category for f in found} == {"token", "credential"}
    assert any(f.kind == "github_token" for f in found)
