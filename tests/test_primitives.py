"""Lint the distributable APM primitives (ADR-0003, ADR-0027)."""

import re
from pathlib import Path

import pytest

from chatur.adr import parse_front_matter
from chatur.policy import load_policy
from chatur.project import SKILL_TEMPLATES, TEMPLATES

REPO = Path(__file__).resolve().parents[1]
APM = REPO / ".apm"
TEMPLATE_DIR = REPO / "src" / "chatur" / "templates"

AGENT_FILES = sorted((APM / "agents").glob("*.agent.md"))
PROMPT_FILES = sorted((APM / "prompts").glob("*.prompt.md"))
SKILL_DIRS = sorted(p for p in (APM / "skills").iterdir() if p.is_dir())
INSTRUCTION_FILES = sorted((APM / "instructions").glob("*.instructions.md"))

PRESERVED_PROMPT_KEYS = {"description", "input", "allowed-tools", "model", "argument-hint"}
PHASE_PROMPTS = ("requirements", "design", "build", "test", "review", "release")
AGENT_NAMES = {p.name.removesuffix(".agent.md") for p in AGENT_FILES}
SKILL_NAMES = {p.name for p in SKILL_DIRS}


def front(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path.name}: front matter must open on line 1"
    return parse_front_matter(text)


def top_level_keys(path: Path) -> set[str]:
    block = path.read_text(encoding="utf-8").split("---\n")[1]
    return {m.group(1) for m in re.finditer(r"(?m)^([A-Za-z][\w-]*):", block)}


# --------------------------------------------------------------------------- agents


def test_nine_agents_match_policy_scopes():
    assert len(AGENT_FILES) == 9
    assert AGENT_NAMES == set(load_policy("standard").agents)


@pytest.mark.parametrize("path", AGENT_FILES, ids=lambda p: p.name)
def test_agent_frontmatter(path):
    fields = front(path)
    assert fields["name"] == path.name.removesuffix(".agent.md")
    assert 40 <= len(fields["description"]) <= 1024
    # ADR-0027: no tools/model, the file is copied verbatim to every assistant
    assert top_level_keys(path) == {"name", "description"}


# --------------------------------------------------------------------------- prompts


def test_expected_commands():
    assert {p.name.removesuffix(".prompt.md") for p in PROMPT_FILES} == {
        "chatur-status",
        "chatur-adr",
        "chatur-check",
        *(f"chatur-{p}" for p in PHASE_PROMPTS),
    }


@pytest.mark.parametrize("path", PROMPT_FILES, ids=lambda p: p.name)
def test_prompt_frontmatter(path):
    assert top_level_keys(path) <= PRESERVED_PROMPT_KEYS, "non-preserved keys are dropped by APM"
    assert front(path)["description"]
    text = path.read_text(encoding="utf-8")
    used = set(re.findall(r"\$\{input:([\w-]+)\}", text))
    declared = set(re.findall(r"(?m)^  - ([\w-]+)$", text.split("---\n")[1]))
    assert used == declared, f"{path.name}: inputs used {used} vs declared {declared}"


@pytest.mark.parametrize("phase", PHASE_PROMPTS)
def test_phase_prompt_ends_with_human_gate_step(phase):
    text = (APM / "prompts" / f"chatur-{phase}.prompt.md").read_text(encoding="utf-8")
    assert f"chatur gate approve {phase}" in text
    assert "chatur gate status" in text


# --------------------------------------------------------------------------- skills


def test_skill_set_matches_templates_map():
    assert SKILL_NAMES == set(SKILL_TEMPLATES)


@pytest.mark.parametrize("path", SKILL_DIRS, ids=lambda p: p.name)
def test_skill_rules(path):
    skill = path / "SKILL.md"
    fields = front(skill)
    assert fields["name"] == path.name
    assert re.fullmatch(r"[a-z0-9-]{1,64}", fields["name"])
    assert fields["description"].startswith("Use when")
    assert len(fields["description"]) <= 1024
    assert len(skill.read_text(encoding="utf-8").splitlines()) < 500


@pytest.mark.parametrize(
    ("skill", "name"),
    [(s, n) for s, names in SKILL_TEMPLATES.items() for n in names],
)
def test_skill_assets_match_templates(skill, name):
    asset = APM / "skills" / skill / "assets" / name
    assert asset.is_file(), "run: python scripts/sync_primitives.py"
    assert asset.read_bytes() == (TEMPLATE_DIR / name).read_bytes(), (
        "template drift; run: python scripts/sync_primitives.py"
    )


def test_every_template_is_shipped_and_used():
    assert {p.name for p in TEMPLATE_DIR.glob("*.md")} == set(TEMPLATES)
    used = {n for names in SKILL_TEMPLATES.values() for n in names}
    assert used == set(TEMPLATES)


# --------------------------------------------------------------------------- instructions


@pytest.mark.parametrize("path", INSTRUCTION_FILES, ids=lambda p: p.name)
def test_instruction_frontmatter(path):
    fields = front(path)
    assert fields["description"] and fields["applyTo"]


# --------------------------------------------------------------------------- cross-references


ALL_TEXT = [*AGENT_FILES, *PROMPT_FILES, *INSTRUCTION_FILES, *(d / "SKILL.md" for d in SKILL_DIRS)]


@pytest.mark.parametrize("path", ALL_TEXT, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_references_resolve(path):
    text = path.read_text(encoding="utf-8")
    for agent in set(
        re.findall(
            r"\b(chatur-(?:orchestrator|product-analyst|architect|security|"
            r"developer|qa|reviewer|devops|docs))\b",
            text,
        )
    ):
        assert agent in AGENT_NAMES
    for skill in set(re.findall(r"`(chatur-[a-z-]+)` skill", text)):
        assert skill in SKILL_NAMES, f"{path.name} references unknown skill {skill}"
    for template in set(re.findall(r"docs/templates/([\w-]+\.md)", text)):
        assert template in TEMPLATES, f"{path.name} references unknown template {template}"


@pytest.mark.parametrize("path", ALL_TEXT, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_primitives_never_tell_agents_to_commit_or_approve(path):
    text = path.read_text(encoding="utf-8").lower()
    # agents may *mention* these as human actions, but never instruct themselves to run them
    assert "run `git commit" not in text and "run `git push" not in text
    assert not re.search(r"\byou (should|must|can) (run )?`?chatur gate approve", text)
