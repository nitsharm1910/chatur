"""Agent least privilege (ADR-0010, ADR-0027) and loader/guard selector consistency."""

import pytest

from chatur import guard, policy
from chatur.events import ChaturEvent, EventKind, ToolCall, ToolCategory
from chatur.policy import PolicyError, load_policy
from chatur.verdict import Decision
from conftest import ROOT, check, hit_ids, shell_event, write_event

AGENTS = (
    "chatur-orchestrator",
    "chatur-reviewer",
    "chatur-product-analyst",
    "chatur-architect",
    "chatur-security",
    "chatur-qa",
    "chatur-developer",
    "chatur-devops",
    "chatur-docs",
)


def agent_write(agent: str | None, path: str) -> ChaturEvent:
    return ChaturEvent(
        kind=EventKind.PRE_TOOL,
        assistant="test",
        session_id="s",
        cwd=ROOT,
        agent=agent,
        tool=ToolCall(
            ToolCategory.FILE_WRITE, "Write", {"file_path": path, "content": "x"}, paths=(path,)
        ),
    )


def scope_hits(event: ChaturEvent, profile: str = "standard") -> set[str]:
    return {h for h in hit_ids(check(event, profile)) if h.startswith("agent.")}


# --------------------------------------------------------------------------- regression


def test_every_policy_selector_is_implemented_by_the_guard():
    # Regression (2026-10-04): selectors accepted by the loader but missing from guard.SELECTORS
    # made rules match EVERY event, which denied all file writes during dogfooding.
    loader_selectors = (
        policy._BOOL_SELECTORS
        | policy._LIST_SELECTORS
        | policy._REGEX_SELECTORS
        | {"contains_secret"}
    )
    assert loader_selectors == set(guard.SELECTORS)


def test_main_session_and_unknown_agents_unaffected():
    assert scope_hits(write_event("src/app.py")) == set()
    assert scope_hits(agent_write(None, "docs/decisions/0001-x.md")) == set()
    assert scope_hits(agent_write("my-own-agent", "anything.txt")) == set()


# --------------------------------------------------------------------------- scopes


def test_baseline_defines_all_nine_agents():
    assert set(load_policy("standard").agents) == set(AGENTS)


@pytest.mark.parametrize("agent", ["chatur-orchestrator", "chatur-reviewer"])
@pytest.mark.parametrize("profile", ["strict", "standard", "relaxed"])
def test_read_only_agents_denied(agent, profile):
    verdict = check(agent_write(agent, "docs/review/report.md"), profile)
    assert verdict.decision is Decision.DENY
    assert "agent.read-only" in hit_ids(verdict)


IN_SCOPE = [
    ("chatur-product-analyst", "docs/requirements/PRD-login.md"),
    ("chatur-architect", "docs/design/login.md"),
    ("chatur-architect", "docs/decisions/0003-use-jwt.md"),
    ("chatur-security", "docs/security/threat-model.md"),
    ("chatur-qa", "tests/test_login.py"),
    ("chatur-qa", "src/auth/login.test.ts"),
    ("chatur-qa", "pkg/auth/login_test.go"),
    ("chatur-qa", "docs/test/test-report-1.md"),
    ("chatur-developer", "src/auth/login.py"),
    ("chatur-developer", "package.json"),
    ("chatur-devops", ".github/workflows/ci.yml"),
    ("chatur-devops", "Dockerfile"),
    ("chatur-devops", "docs/releases/v1.0.0.md"),
    ("chatur-docs", "README.md"),
    ("chatur-docs", "docs/user-guide.md"),
]


@pytest.mark.parametrize(("agent", "path"), IN_SCOPE)
def test_in_scope_writes_pass_scope_rules(agent, path):
    assert scope_hits(agent_write(agent, path), "strict") == set()


OUT_OF_SCOPE = [
    ("chatur-product-analyst", "src/app.py"),
    ("chatur-architect", "src/app.py"),
    ("chatur-security", "docs/design/x.md"),
    ("chatur-qa", "src/auth/login.py"),
    ("chatur-developer", "docs/decisions/0009-x.md"),
    ("chatur-developer", ".github/workflows/ci.yml"),
    ("chatur-developer", "CHANGELOG.md"),
    ("chatur-devops", "src/app.py"),
    ("chatur-docs", "docs/requirements/PRD.md"),
    ("chatur-docs", "src/app.py"),
    ("chatur-developer", "/etc/passwd"),  # outside the project
]


@pytest.mark.parametrize(("agent", "path"), OUT_OF_SCOPE)
def test_out_of_scope_writes(agent, path):
    assert check(agent_write(agent, path), "strict").decision is Decision.DENY
    standard = check(agent_write(agent, path), "standard")
    assert "agent.write-scope" in hit_ids(standard)
    assert standard.decision.blocks


def test_write_without_path_is_out_of_scope():
    event = ChaturEvent(
        kind=EventKind.PRE_TOOL,
        assistant="t",
        session_id="s",
        cwd=ROOT,
        agent="chatur-qa",
        tool=ToolCall(ToolCategory.FILE_WRITE, "Write", {"content": "x"}),
    )
    assert "agent.write-scope" in scope_hits(event)


def test_scopes_only_apply_to_file_writes():
    shell = ChaturEvent(
        kind=EventKind.PRE_TOOL,
        assistant="t",
        session_id="s",
        cwd=ROOT,
        agent="chatur-reviewer",
        tool=ToolCall(ToolCategory.SHELL, "Bash", {}, command="pytest -q"),
    )
    assert scope_hits(shell) == set()
    assert scope_hits(shell_event("ls")) == set()


# --------------------------------------------------------------------------- schema


HEADER = 'schema = "chatur.policy/v1"\nkind = "local"\n'


def test_local_can_add_new_agent(tmp_path):
    path = tmp_path / "local.toml"
    path.write_text(HEADER + '[agents.data-engineer]\nwrite = ["pipelines/**"]\n', encoding="utf-8")
    scope = load_policy("standard", local_path=path).agents["data-engineer"]
    assert scope.write == ("pipelines/**",) and scope.source == "local"


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ('[agents.chatur-qa]\nwrite = ["**"]\n', "agent scopes can't be modified"),
        ("[agents.x]\nread_only = true\nwrite = ['a']\n", "can't have write/exclude"),
        ("[agents.x]\n", "needs read_only = true or at least one write glob"),
        ("[agents.x]\nwrites = ['a']\n", "unknown key 'writes'"),
        ("[agents.Bad_Name]\nread_only = true\n", "agent name must match"),
    ],
)
def test_agent_scope_rejections(tmp_path, body, expected):
    path = tmp_path / "local.toml"
    path.write_text(HEADER + body, encoding="utf-8")
    with pytest.raises(PolicyError) as exc:
        load_policy("standard", local_path=path)
    assert expected in "\n".join(exc.value.problems)
