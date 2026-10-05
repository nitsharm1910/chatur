"""Policy loader: shipped profiles, ADR-0007 table, every tighten-only rejection (ADR-0016)."""

import json
import shutil
from pathlib import Path

import pytest

from chatur.cli import main
from chatur.events import EventKind, ToolCategory
from chatur.policy import (
    PolicyError,
    load_policy,
    load_project_policy,
    packaged_policy_dir,
)
from chatur.verdict import Decision

BASELINE_IDS = {
    "git.no-commit-push",
    "git.no-history-rewrite",
    "git.remote-tools",
    "git.remote-cli",
    "gate.state-protected",
    "gate.no-agent-approval",
    "secrets.known-token",
    "secrets.credential-shape",
    "secrets.in-prompt",
    "agent.read-only",
    "fs.change-needs-approval",
    "exec.needs-approval",
    "exec.no-new-executables",
}
HEADER = 'schema = "chatur.policy/v1"\nkind = "local"\n'


def _local(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "policy.local.toml"
    path.write_text(HEADER + body, encoding="utf-8")
    return path


def _problems(exc: pytest.ExceptionInfo[PolicyError]) -> str:
    return "\n".join(exc.value.problems)


# --------------------------------------------------------------------------- shipped policies


@pytest.mark.parametrize("profile", ["strict", "standard", "relaxed"])
def test_shipped_profiles_load_with_full_baseline(profile):
    policy = load_policy(profile)
    ids = {r.id for r in policy.rules}
    assert ids >= BASELINE_IDS
    assert policy.sources == ("baseline", f"profile:{profile}")
    for rule_id in BASELINE_IDS:
        rule = policy.rule(rule_id)
        assert rule.baseline and rule.source == "baseline"


@pytest.mark.parametrize(
    ("profile", "rule_id", "expected"),
    [
        # ADR-0014 baseline: identical in every profile
        *[(p, "git.no-commit-push", Decision.DENY) for p in ("strict", "standard", "relaxed")],
        *[(p, "exec.needs-approval", Decision.ASK) for p in ("strict", "standard", "relaxed")],
        *[(p, "fs.change-needs-approval", Decision.ASK) for p in ("strict", "standard", "relaxed")],
        *[(p, "gate.state-protected", Decision.DENY) for p in ("strict", "standard", "relaxed")],
        # ADR-0007 table
        ("strict", "fs.protected-paths", Decision.DENY),
        ("standard", "fs.protected-paths", Decision.ASK),
        ("relaxed", "fs.protected-paths", Decision.WARN),
        ("strict", "gate.design-before-code", Decision.DENY),
        ("standard", "gate.design-before-code", Decision.WARN),
        ("strict", "test.missing-tests", Decision.DENY),
        ("standard", "test.missing-tests", Decision.WARN),
        ("strict", "deps.needs-adr", Decision.DENY),
        ("standard", "deps.needs-adr", Decision.WARN),
        ("strict", "net.web-tools", Decision.ASK),
        ("standard", "net.web-tools", Decision.LOG),
        ("relaxed", "net.web-tools", Decision.LOG),
    ],
)
def test_adr_0007_table(profile, rule_id, expected):
    assert load_policy(profile).rule(rule_id).verdict is expected


@pytest.mark.parametrize(
    "rule_id", ["gate.design-before-code", "test.missing-tests", "deps.needs-adr"]
)
def test_relaxed_turns_process_rules_off(rule_id):
    with pytest.raises(KeyError):
        load_policy("relaxed").rule(rule_id)


def test_ask_rules_deny_when_unattended():
    policy = load_policy("standard")
    assert policy.rule("exec.needs-approval").unattended is Decision.DENY
    assert policy.rule("net.web-tools").unattended is Decision.LOG


def test_defaults():
    assert load_policy("standard").defaults.unknown_tool is Decision.ASK
    assert load_policy("strict").defaults.unknown_tool is Decision.DENY
    assert load_policy("relaxed").defaults.adapter_error is Decision.DENY


def test_readonly_allowlist_disabled_by_default():
    assert load_policy("standard").readonly_allowlist == ()


def test_rule_fields_parsed():
    rule = load_policy("standard").rule("test.missing-tests")
    assert rule.events == (EventKind.STOP,)
    assert rule.tool_categories == ()
    exec_rule = load_policy("standard").rule("exec.needs-approval")
    assert exec_rule.tool_categories == (ToolCategory.SHELL,)
    assert exec_rule.events == (EventKind.PRE_TOOL,)


# --------------------------------------------------------------------------- local: allowed


def test_local_can_add_rule(tmp_path):
    local = _local(
        tmp_path,
        """
[[rule]]
id = "local.no-prod-config"
applies_to = { tool_category = ["file_write"] }
match.path_globs = ["config/prod/**"]
verdict = "deny"
reason = "Prod config is managed by the platform team."
""",
    )
    policy = load_policy("standard", local_path=local)
    rule = policy.rule("local.no-prod-config")
    assert rule.source == "local" and rule.verdict is Decision.DENY
    assert policy.sources[-1] == "local"


def test_local_can_tighten_baseline_and_profile_rules(tmp_path):
    local = _local(
        tmp_path,
        """
[tighten."exec.needs-approval"]
verdict = "deny"

[tighten."test.missing-tests"]
verdict = "ask"
""",
    )
    policy = load_policy("standard", local_path=local)
    exec_rule = policy.rule("exec.needs-approval")
    assert exec_rule.verdict is Decision.DENY
    assert exec_rule.tightened_by == ("local",)
    tests_rule = policy.rule("test.missing-tests")
    assert tests_rule.verdict is Decision.ASK
    assert tests_rule.unattended is Decision.ASK  # raised to stay >= verdict


def test_local_can_tighten_defaults_and_add_redaction(tmp_path):
    local = _local(
        tmp_path,
        """
[defaults]
unknown_tool = "deny"

[redact]
extra_patterns = ['\\bACME-[0-9]{8}\\b']
""",
    )
    policy = load_policy("standard", local_path=local)
    assert policy.defaults.unknown_tool is Decision.DENY
    assert policy.redact_patterns == (r"\bACME-[0-9]{8}\b",)


# --------------------------------------------------------------------------- local: rejected


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        pytest.param(
            '[tighten."git.no-commit-push"]\nverdict = "allow"\n',
            "cannot loosen deny -> allow",
            id="loosen-baseline",
        ),
        pytest.param(
            '[tighten."fs.protected-paths"]\nverdict = "warn"\n',
            "cannot loosen ask -> warn",
            id="loosen-profile-rule",
        ),
        pytest.param(
            '[tighten."exec.needs-approval"]\nunattended = "ask"\n',
            "cannot loosen deny -> ask",
            id="loosen-unattended",
        ),
        pytest.param(
            '[defaults]\nadapter_error = "allow"\n',
            "cannot loosen deny -> allow",
            id="loosen-defaults",
        ),
        pytest.param(
            '[[rule]]\nid = "exec.needs-approval"\nmatch.any = true\nverdict = "allow"\n'
            'reason = "x"\n',
            "already defined by baseline",
            id="redefine-baseline",
        ),
        pytest.param(
            '[[rule]]\nid = "x.y"\nbaseline = true\nmatch.any = true\nverdict = "deny"\n'
            'reason = "x"\n',
            "only the baseline file may declare baseline rules",
            id="local-baseline-flag",
        ),
        pytest.param(
            "[readonly_allowlist]\nenabled = true\n",
            "unknown key 'readonly_allowlist'",
            id="enable-allowlist",
        ),
        pytest.param(
            '[[rule]]\nid = "x.y"\nmatch.any = true\nverdcit = "deny"\nreason = "x"\n',
            "unknown key 'verdcit'",
            id="typo-key",
        ),
        pytest.param(
            '[[rule]]\nid = "x.y"\nmatch.anything = true\nverdict = "deny"\nreason = "x"\n',
            "unknown key 'anything'",
            id="typo-match-key",
        ),
        pytest.param(
            '[tighten."no.such-rule"]\nverdict = "deny"\n',
            "no such rule",
            id="tighten-unknown",
        ),
        pytest.param(
            '[[rule]]\nid = "x.y"\nmatch.shell_patterns = ["(unclosed"]\nverdict = "deny"\n'
            'reason = "x"\n',
            "invalid regex",
            id="bad-regex",
        ),
        pytest.param(
            '[[rule]]\nid = "x.y"\nmatch.any = true\nverdict = "deny"\nunattended = "allow"\n'
            'reason = "x"\n',
            "weaker than 'verdict'",
            id="unattended-weaker",
        ),
        pytest.param(
            '[[rule]]\nid = "x.y"\ncritical = true\nmatch.any = true\nverdict = "deny"\n'
            'reason = "x"\n',
            "critical rules need a 'git' or 'ci' layer",
            id="critical-hook-only",
        ),
        pytest.param(
            '[[rule]]\nid = "x.y"\nmatch.requires_gate = "deploy"\nverdict = "deny"\n'
            'reason = "x"\n',
            "unknown phase",
            id="bad-phase",
        ),
        pytest.param(
            '[[rule]]\nid = "x.y"\nverdict = "deny"\nreason = "x"\n',
            "match: required",
            id="missing-match",
        ),
        pytest.param(
            '[[rule]]\nid = "x.y"\nmatch.any = true\nverdict = "block"\nreason = "x"\n',
            "invalid decision 'block'",
            id="bad-decision",
        ),
    ],
)
def test_local_rejections(tmp_path, body, expected):
    with pytest.raises(PolicyError) as exc:
        load_policy("standard", local_path=_local(tmp_path, body))
    assert expected in _problems(exc)


def test_all_problems_reported_at_once(tmp_path):
    local = _local(
        tmp_path,
        '[tighten."git.no-commit-push"]\nverdict = "allow"\n'
        '[defaults]\nunknown_tool = "allow"\n'
        "[bogus]\nx = 1\n",
    )
    with pytest.raises(PolicyError) as exc:
        load_policy("standard", local_path=local)
    assert len(exc.value.problems) == 3


def test_local_wrong_kind_rejected(tmp_path):
    path = tmp_path / "policy.local.toml"
    path.write_text('schema = "chatur.policy/v1"\nkind = "baseline"\n', encoding="utf-8")
    with pytest.raises(PolicyError) as exc:
        load_policy("standard", local_path=path)
    assert "kind must be 'local'" in _problems(exc)


def test_local_invalid_toml(tmp_path):
    path = tmp_path / "policy.local.toml"
    path.write_text("this is = = not toml", encoding="utf-8")
    with pytest.raises(PolicyError) as exc:
        load_policy("standard", local_path=path)
    assert "invalid TOML" in _problems(exc)


# --------------------------------------------------------------------------- profiles


@pytest.mark.parametrize("name", ["../etc/passwd", "baseline", "Strict", "", "a/b"])
def test_invalid_profile_names(name):
    with pytest.raises(PolicyError, match="invalid profile name"):
        load_policy(name)


def test_missing_profile():
    with pytest.raises(PolicyError, match="file not found"):
        load_policy("nonexistent")


def test_custom_profile_cannot_redefine_baseline(tmp_path):
    policy_dir = tmp_path / "policies"
    shutil.copytree(Path(str(packaged_policy_dir())), policy_dir)
    (policy_dir / "custom.toml").write_text(
        'schema = "chatur.policy/v1"\nkind = "profile"\nname = "custom"\n'
        '[[rule]]\nid = "git.no-commit-push"\nmatch.any = true\nverdict = "allow"\nreason = "x"\n',
        encoding="utf-8",
    )
    with pytest.raises(PolicyError, match="already defined by baseline"):
        load_policy("custom", policy_dir=policy_dir)


def test_baseline_rule_without_flag_rejected(tmp_path):
    policy_dir = tmp_path / "policies"
    shutil.copytree(Path(str(packaged_policy_dir())), policy_dir)
    base = policy_dir / "baseline.toml"
    base.write_text(
        base.read_text(encoding="utf-8").replace(
            'id = "exec.needs-approval"\nadr = "ADR-0014"\nbaseline = true\n',
            'id = "exec.needs-approval"\nadr = "ADR-0014"\n',
        ),
        encoding="utf-8",
    )
    with pytest.raises(PolicyError, match="must set baseline = true"):
        load_policy("standard", policy_dir=policy_dir)


# --------------------------------------------------------------------------- project + CLI


def test_project_policy_reads_config_and_local(tmp_path):
    chatur_dir = tmp_path / ".chatur"
    chatur_dir.mkdir()
    (chatur_dir / "config.toml").write_text('[policy]\nprofile = "strict"\n', encoding="utf-8")
    (chatur_dir / "policy.local.toml").write_text(
        HEADER + '[tighten."net.web-tools"]\nverdict = "deny"\n', encoding="utf-8"
    )
    policy = load_project_policy(tmp_path)
    assert policy.profile == "strict"
    assert policy.rule("net.web-tools").verdict is Decision.DENY


def test_project_policy_defaults_to_standard(tmp_path):
    assert load_project_policy(tmp_path).profile == "standard"


def test_cli_validate_ok(tmp_path, capsys):
    assert main(["policy", "validate", "--root", str(tmp_path)]) == 0
    assert "policy OK: profile=standard" in capsys.readouterr().out


def test_cli_validate_reports_errors(tmp_path, capsys):
    (tmp_path / ".chatur").mkdir()
    (tmp_path / ".chatur" / "policy.local.toml").write_text(
        HEADER + '[tighten."git.no-commit-push"]\nverdict = "allow"\n', encoding="utf-8"
    )
    assert main(["policy", "validate", "--root", str(tmp_path)]) == 1
    assert "cannot loosen" in capsys.readouterr().err


def test_cli_show_json(tmp_path, capsys):
    assert main(["policy", "show", "--root", str(tmp_path), "--profile", "strict", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["profile"] == "strict"
    assert data["defaults"]["unknown_tool"] == "deny"
    assert {r["id"] for r in data["rules"]} >= BASELINE_IDS


def test_cli_show_table(tmp_path, capsys):
    assert main(["policy", "show", "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "git.no-commit-push" in out and "deny" in out
