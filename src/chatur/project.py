"""`chatur init`: prepare a target project for Chatur (ADR-0011, ADR-0022). Stdlib-only.

Creates only what is missing; never overwrites docs, state, or the audit log.
"""

from __future__ import annotations

import tomllib
from collections.abc import Sequence
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from chatur.adr import packaged_template
from chatur.policy import load_policy, load_project_policy

ASSISTANTS = ("claude", "copilot", "codex", "gemini", "cursor")
FULL_SUPPORT = frozenset({"claude", "copilot"})  # ADR-0009
DEFAULT_ASSISTANTS = ("claude", "copilot")

DOC_FOLDERS = {
    "requirements": "Requirements: PRDs, user stories, acceptance criteria. Gate: requirements.",
    "design": "Design documents and interfaces. Gate: design (with docs/security threat model).",
    "decisions": 'Architecture Decision Records. Create with `chatur adr new "<title>"`.',
    "security": "Threat models and security reviews.",
    "test": "Test plans and test reports. Gate: test.",
    "review": "Code review reports. Gate: review.",
    "releases": "Release notes. Gate: release (with CHANGELOG.md).",
}

# SDLC templates shipped in the wheel (ADR-0027): installed to docs/templates/ by init, and copied
# into the APM skills' assets/ (kept identical by tests/test_primitives.py).
TEMPLATES = (
    "prd.md",
    "design.md",
    "threat-model.md",
    "test-plan.md",
    "test-report.md",
    "review.md",
    "release-notes.md",
    "adr.md",
)
SKILL_TEMPLATES = {
    "chatur-write-prd": ("prd.md",),
    "chatur-design-doc": ("design.md",),
    "chatur-threat-model": ("threat-model.md",),
    "chatur-test-plan": ("test-plan.md", "test-report.md"),
    "chatur-code-review": ("review.md",),
    "chatur-release-notes": ("release-notes.md",),
    "chatur-adr": ("adr.md",),
}

GITIGNORE_BEGIN = "# >>> chatur (managed by `chatur init`) >>>"
GITIGNORE_END = "# <<< chatur <<<"

CONFIG_TEMPLATE = """\
# Chatur project configuration (ADR-0022). Check it with: chatur policy validate
schema = "chatur.config/v1"

[policy]
profile = "{profile}"   # strict | standard | relaxed (ADR-0007)

[assistants]
enabled = [{assistants}]   # full: claude, copilot; instructions-only: codex, gemini, cursor

[audit]
commit = {commit}   # commit .chatur/audit/ to git (ADR-0019, ADR-0022)

# Override which files a gate approval covers (ADR-0021). Default for design:
# [gates.design]
# artifacts = ["docs/design/**/*.md", "docs/security/threat-model*.md"]
"""

LOCAL_POLICY_TEMPLATE = """\
# Project-local policy: may ADD rules and TIGHTEN existing ones, never loosen (ADR-0016).
# Check it with: chatur policy validate    Inspect the result: chatur policy show
schema = "chatur.policy/v1"
kind = "local"

# Example: block edits to production config.
# [[rule]]
# id = "local.no-prod-config"
# applies_to = { tool_category = ["file_write", "shell"] }
# match.path_globs = ["config/prod/**"]
# verdict = "deny"
# reason = "Production config is changed by the platform team."

# Example: require approval for web access.
# [tighten."net.web-tools"]
# verdict = "ask"

# Example: mask project-specific identifiers in the audit log (ADR-0015).
# [redact]
# extra_patterns = ['\\bACME-[0-9]{8}\\b']
"""


class InitError(ValueError):
    pass


def template_text(name: str) -> str:
    return resources.files("chatur").joinpath("templates", name).read_text(encoding="utf-8")


@dataclass
class InitResult:
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _write_new(root: Path, rel: str, content: str, result: InitResult) -> None:
    path = root / rel
    if path.exists():
        result.skipped.append(rel)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    result.created.append(rel)


def gitignore_block(commit_audit: bool) -> str:
    lines = [GITIGNORE_BEGIN, ".chatur/audit/.lock", ".chatur/state.json.tmp"]
    if not commit_audit:
        lines.append(".chatur/audit/")
    lines.append(GITIGNORE_END)
    return "\n".join(lines) + "\n"


def _update_gitignore(root: Path, commit_audit: bool, result: InitResult) -> None:
    path = root / ".gitignore"
    block = gitignore_block(commit_audit)
    if not path.exists():
        path.write_text(block, encoding="utf-8")
        result.created.append(".gitignore")
        return
    text = path.read_text(encoding="utf-8")
    start, end = text.find(GITIGNORE_BEGIN), text.find(GITIGNORE_END)
    if start != -1 and end != -1:
        new_text = text[:start] + block + text[end + len(GITIGNORE_END) :].lstrip("\n")
    else:
        new_text = text + ("" if text.endswith("\n") or not text else "\n") + block
    if new_text == text:
        result.skipped.append(".gitignore")
    else:
        path.write_text(new_text, encoding="utf-8")
        result.updated.append(".gitignore")


def _configured_commit(config: Path, *, default: bool) -> bool:
    """An existing config's [audit] commit wins over the profile default."""
    try:
        value = tomllib.loads(config.read_text(encoding="utf-8")).get("audit", {}).get("commit")
    except (OSError, tomllib.TOMLDecodeError):
        return default
    return value if isinstance(value, bool) else default


def init_project(
    root: Path,
    *,
    profile: str = "standard",
    assistants: Sequence[str] = DEFAULT_ASSISTANTS,
    force: bool = False,
) -> InitResult:
    # Validate everything before writing anything.
    load_policy(profile)  # raises PolicyError for unknown/invalid profiles
    chosen = list(dict.fromkeys(a.strip().lower() for a in assistants if a.strip()))
    unknown = [a for a in chosen if a not in ASSISTANTS]
    if unknown or not chosen:
        raise InitError(f"unknown assistant(s) {unknown or chosen}; choose from {list(ASSISTANTS)}")

    result = InitResult()
    commit_audit = profile != "relaxed"
    config_rel = ".chatur/config.toml"
    config = CONFIG_TEMPLATE.format(
        profile=profile,
        assistants=", ".join(f'"{a}"' for a in chosen),
        commit=str(commit_audit).lower(),
    )
    if force and (root / config_rel).exists():
        (root / config_rel).write_text(config, encoding="utf-8")
        result.updated.append(config_rel)
    else:
        _write_new(root, config_rel, config, result)
    commit_audit = _configured_commit(root / config_rel, default=commit_audit)
    _write_new(root, ".chatur/policy.local.toml", LOCAL_POLICY_TEMPLATE, result)
    for folder, purpose in DOC_FOLDERS.items():
        _write_new(root, f"docs/{folder}/README.md", f"# {folder.title()}\n\n{purpose}\n", result)
    _write_new(root, "docs/decisions/0000-template.md", packaged_template(), result)
    for name in TEMPLATES:
        _write_new(root, f"docs/templates/{name}", template_text(name), result)
    _update_gitignore(root, commit_audit, result)

    load_project_policy(root)  # the written config + local policy must compose cleanly
    for name in chosen:
        if name not in FULL_SUPPORT:
            result.notes.append(
                f"{name}: instructions-only until its adapter lands; "
                "git/CI backstop applies (ADR-0009)"
            )
    result.notes.append("next: `apm install nitsharm1910/chatur` to add agents/prompts/hooks")
    return result
