"""Policy loading and tighten-only composition (ADR-0007, ADR-0014, ADR-0016).

Stdlib-only (ADR-0012). Layers: baseline -> profile -> project-local. Later layers may add rules
and tighten existing ones; any loosening is a load error. All problems are reported together.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

from chatur.events import EventKind, ToolCategory
from chatur.verdict import Decision

SCHEMA = "chatur.policy/v1"
DEFAULT_PROFILE = "standard"
LAYERS = frozenset({"hook", "git", "ci"})
PHASES = frozenset({"requirements", "design", "build", "test", "review", "release"})

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.\-]*$")
_PROFILE_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]*$")

_RULE_KEYS = frozenset(
    {"id", "adr", "description", "baseline", "critical", "layers", "applies_to", "match"}
    | {"verdict", "unattended", "reason"}
)
_APPLIES_KEYS = frozenset({"tool_category", "events"})
_BOOL_SELECTORS = frozenset({"any", "file_write", "shebang"})
_LIST_SELECTORS = frozenset({"path_globs", "git_subcommands"})
_REGEX_SELECTORS = frozenset(
    {"shell_patterns", "git_patterns", "argv_patterns", "tool_name_patterns"}  # argv: ADR-0018
)
_BOOL_CONDITIONS = frozenset({"requires_adr", "missing_tests"})
_MATCH_KEYS = (
    _BOOL_SELECTORS | _LIST_SELECTORS | _REGEX_SELECTORS | _BOOL_CONDITIONS | {"requires_gate"}
)
_DEFAULT_KEYS = ("unknown_tool", "unparseable_command", "adapter_error")
_TOP_KEYS = {
    "baseline": frozenset(
        {"schema", "kind", "description", "defaults", "rule", "readonly_allowlist"}
    ),
    "profile": frozenset({"schema", "kind", "name", "description", "defaults", "rule", "tighten"}),
    "local": frozenset({"schema", "kind", "description", "defaults", "rule", "tighten", "redact"}),
}


class PolicyError(ValueError):
    def __init__(self, problems: Iterable[str]) -> None:
        self.problems = list(problems)
        super().__init__("invalid policy:\n" + "\n".join(f"  - {p}" for p in self.problems))


@dataclass(frozen=True, slots=True)
class Rule:
    id: str
    verdict: Decision
    unattended: Decision
    reason: str
    source: str  # "baseline", "profile:<name>", "local"
    adr: str | None = None
    description: str | None = None
    baseline: bool = False
    critical: bool = False
    layers: tuple[str, ...] = ("hook",)
    tool_categories: tuple[ToolCategory, ...] = ()  # empty = any tool
    events: tuple[EventKind, ...] = (EventKind.PRE_TOOL,)
    match: Mapping[str, Any] = field(default_factory=dict)
    tightened_by: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Defaults:
    unknown_tool: Decision = Decision.ASK
    unparseable_command: Decision = Decision.ASK
    adapter_error: Decision = Decision.DENY


@dataclass(frozen=True, slots=True)
class Policy:
    profile: str
    rules: tuple[Rule, ...]
    defaults: Defaults = field(default_factory=Defaults)
    readonly_allowlist: tuple[str, ...] = ()  # regexes; empty unless enabled in baseline
    redact_patterns: tuple[str, ...] = ()  # extra regexes from the local file (ADR-0015)
    sources: tuple[str, ...] = ()

    def rule(self, rule_id: str) -> Rule:
        for r in self.rules:
            if r.id == rule_id:
                return r
        raise KeyError(rule_id)


# --------------------------------------------------------------------------- parsing helpers


def _decision(value: Any, where: str, problems: list[str]) -> Decision | None:
    try:
        return Decision(value)
    except ValueError:
        allowed = ", ".join(d.value for d in Decision)
        problems.append(f"{where}: invalid decision {value!r} (allowed: {allowed})")
        return None


def _str_list(value: Any, where: str, problems: list[str]) -> list[str] | None:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        problems.append(f"{where}: must be a list of strings")
        return None
    return value


def _regex_list(value: Any, where: str, problems: list[str]) -> list[str] | None:
    items = _str_list(value, where, problems)
    if items is None:
        return None
    for pattern in items:
        try:
            re.compile(pattern)
        except re.error as exc:
            problems.append(f"{where}: invalid regex {pattern!r}: {exc}")
    return items


def _unknown_keys(data: Mapping[str, Any], allowed: Iterable[str], where: str, problems: list[str]):
    for key in sorted(set(data) - set(allowed)):
        problems.append(f"{where}: unknown key {key!r}")


def _parse_match(data: Any, where: str, problems: list[str]) -> dict[str, Any]:
    if not isinstance(data, Mapping) or not data:
        problems.append(f"{where}.match: required, with at least one key")
        return {}
    _unknown_keys(data, _MATCH_KEYS, f"{where}.match", problems)
    out: dict[str, Any] = {}
    for key, value in data.items():
        at = f"{where}.match.{key}"
        if key in _BOOL_SELECTORS | _BOOL_CONDITIONS:
            if not isinstance(value, bool):
                problems.append(f"{at}: must be true/false")
            out[key] = value
        elif key in _LIST_SELECTORS:
            out[key] = tuple(_str_list(value, at, problems) or ())
        elif key in _REGEX_SELECTORS:
            out[key] = tuple(_regex_list(value, at, problems) or ())
        elif key == "requires_gate":
            if value not in PHASES:
                problems.append(f"{at}: unknown phase {value!r} (allowed: {sorted(PHASES)})")
            out[key] = value
    return out


def _parse_rule(data: Any, source: str, problems: list[str]) -> Rule | None:
    if not isinstance(data, Mapping):
        problems.append(f"{source}: each [[rule]] must be a table")
        return None
    rule_id = data.get("id")
    where = f"{source} rule {rule_id!r}"
    if not isinstance(rule_id, str) or not _ID_RE.match(rule_id):
        problems.append(f"{where}: 'id' must match {_ID_RE.pattern}")
        return None
    start = len(problems)
    _unknown_keys(data, _RULE_KEYS, where, problems)

    reason = data.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        problems.append(f"{where}: 'reason' is required")
    if "verdict" not in data:
        problems.append(f"{where}: 'verdict' is required")
    verdict = _decision(data.get("verdict"), f"{where}.verdict", problems) or Decision.DENY
    default_unattended = Decision.DENY if verdict is Decision.ASK else verdict
    unattended = default_unattended
    if "unattended" in data:
        unattended = _decision(data["unattended"], f"{where}.unattended", problems) or Decision.DENY
    if unattended.severity < verdict.severity:
        problems.append(
            f"{where}: 'unattended' ({unattended}) is weaker than 'verdict' ({verdict})"
        )

    baseline = data.get("baseline", False)
    if source == "baseline" and baseline is not True:
        problems.append(f"{where}: every rule in the baseline file must set baseline = true")
    if source != "baseline" and baseline:
        problems.append(f"{where}: only the baseline file may declare baseline rules")

    layers = tuple(_str_list(data.get("layers", ["hook"]), f"{where}.layers", problems) or ())
    if not layers or set(layers) - LAYERS:
        problems.append(f"{where}.layers: must be a non-empty subset of {sorted(LAYERS)}")
    critical = data.get("critical", False)
    if critical and not {"git", "ci"} & set(layers):
        problems.append(f"{where}: critical rules need a 'git' or 'ci' layer (ADR-0005)")

    applies = data.get("applies_to", {})
    categories: list[ToolCategory] = []
    events: list[EventKind] = [EventKind.PRE_TOOL]
    if not isinstance(applies, Mapping):
        problems.append(f"{where}.applies_to: must be a table")
    else:
        _unknown_keys(applies, _APPLIES_KEYS, f"{where}.applies_to", problems)
        for name in _str_list(applies.get("tool_category", []), where, problems) or ():
            try:
                categories.append(ToolCategory(name))
            except ValueError:
                problems.append(f"{where}.applies_to.tool_category: unknown category {name!r}")
        if "events" in applies:
            events = []
            for name in _str_list(applies["events"], where, problems) or ():
                try:
                    events.append(EventKind(name))
                except ValueError:
                    problems.append(f"{where}.applies_to.events: unknown event {name!r}")

    match = _parse_match(data.get("match"), where, problems)
    if len(problems) > start:
        return None
    return Rule(
        id=rule_id,
        verdict=verdict,
        unattended=unattended,
        reason=reason,
        source=source,
        adr=data.get("adr"),
        description=data.get("description"),
        baseline=bool(baseline),
        critical=bool(critical),
        layers=layers,
        tool_categories=tuple(categories),
        events=tuple(events),
        match=match,
    )


def _read_doc(path: Path | Traversable, kind: str, problems: list[str]) -> dict[str, Any] | None:
    label = f"{kind} ({path})"
    try:
        doc = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        problems.append(f"{label}: file not found")
        return None
    except tomllib.TOMLDecodeError as exc:
        problems.append(f"{label}: invalid TOML: {exc}")
        return None
    if doc.get("schema") != SCHEMA:
        problems.append(f"{label}: schema must be {SCHEMA!r}, got {doc.get('schema')!r}")
    if doc.get("kind") != kind:
        problems.append(f"{label}: kind must be {kind!r}, got {doc.get('kind')!r}")
    _unknown_keys(doc, _TOP_KEYS[kind], label, problems)
    return doc


# --------------------------------------------------------------------------- composition


def _apply_defaults(current: Defaults, data: Any, where: str, problems: list[str]) -> Defaults:
    if not isinstance(data, Mapping):
        problems.append(f"{where}.defaults: must be a table")
        return current
    _unknown_keys(data, _DEFAULT_KEYS, f"{where}.defaults", problems)
    changes: dict[str, Decision] = {}
    for key in _DEFAULT_KEYS:
        if key not in data:
            continue
        new = _decision(data[key], f"{where}.defaults.{key}", problems)
        old: Decision = getattr(current, key)
        if new is None:
            continue
        if new.severity < old.severity:
            problems.append(f"{where}.defaults.{key}: cannot loosen {old} -> {new} (tighten-only)")
        else:
            changes[key] = new
    return replace(current, **changes)


def _apply_tighten(rules: dict[str, Rule], data: Any, source: str, problems: list[str]) -> None:
    if not isinstance(data, Mapping):
        problems.append(f"{source}.tighten: must be a table")
        return
    for rule_id, spec in data.items():
        where = f"{source}.tighten.{rule_id}"
        if rule_id not in rules:
            problems.append(f"{where}: no such rule")
            continue
        if not isinstance(spec, Mapping):
            problems.append(f"{where}: must be a table")
            continue
        _unknown_keys(spec, ("verdict", "unattended"), where, problems)
        rule = rules[rule_id]
        verdict, unattended = rule.verdict, rule.unattended
        for key in ("verdict", "unattended"):
            if key not in spec:
                continue
            new = _decision(spec[key], f"{where}.{key}", problems)
            old = getattr(rule, key)
            if new is None:
                continue
            if new.severity < old.severity:
                problems.append(f"{where}.{key}: cannot loosen {old} -> {new} (tighten-only)")
            elif key == "verdict":
                verdict = new
            else:
                unattended = new
        # Unattended is never weaker than attended.
        if unattended.severity < verdict.severity:
            unattended = verdict
        rules[rule_id] = replace(
            rule,
            verdict=verdict,
            unattended=unattended,
            tightened_by=(*rule.tightened_by, source),
        )


def _apply_layer(
    rules: dict[str, Rule],
    defaults: Defaults,
    doc: Mapping[str, Any],
    source: str,
    problems: list[str],
) -> Defaults:
    if "defaults" in doc:
        defaults = _apply_defaults(defaults, doc["defaults"], source, problems)
    raw_rules = doc.get("rule", [])
    if not isinstance(raw_rules, list):
        problems.append(f"{source}: 'rule' must be an array of tables ([[rule]])")
        raw_rules = []
    for raw in raw_rules:
        rule = _parse_rule(raw, source, problems)
        if rule is None:
            continue
        if rule.id in rules:
            problems.append(
                f"{source} rule {rule.id!r}: already defined by {rules[rule.id].source}; "
                f"use [tighten.{rule.id!r}] instead of redefining"
            )
            continue
        rules[rule.id] = rule
    if "tighten" in doc:
        _apply_tighten(rules, doc["tighten"], source, problems)
    return defaults


def packaged_policy_dir() -> Traversable:
    return resources.files("chatur").joinpath("policies")


def load_policy(
    profile: str = DEFAULT_PROFILE,
    *,
    local_path: Path | None = None,
    policy_dir: Path | Traversable | None = None,
) -> Policy:
    """Compose baseline + profile (+ local). Raises PolicyError listing every problem."""
    problems: list[str] = []
    directory = policy_dir if policy_dir is not None else packaged_policy_dir()

    if not _PROFILE_RE.match(profile) or profile == "baseline":
        raise PolicyError([f"invalid profile name {profile!r}"])

    rules: dict[str, Rule] = {}
    defaults = Defaults()
    allowlist: tuple[str, ...] = ()
    redact_patterns: tuple[str, ...] = ()
    sources: list[str] = []

    base = _read_doc(directory.joinpath("baseline.toml"), "baseline", problems)
    if base is not None:
        sources.append("baseline")
        defaults = _apply_layer(rules, defaults, base, "baseline", problems)
        allow = base.get("readonly_allowlist", {})
        if isinstance(allow, Mapping):
            _unknown_keys(allow, ("enabled", "commands"), "baseline.readonly_allowlist", problems)
            commands = _regex_list(
                allow.get("commands", []), "baseline.readonly_allowlist.commands", problems
            )
            if allow.get("enabled") is True and commands:
                allowlist = tuple(commands)

    prof = _read_doc(directory.joinpath(f"{profile}.toml"), "profile", problems)
    if prof is not None:
        if prof.get("name") != profile:
            problems.append(f"profile:{profile}: 'name' must be {profile!r}")
        sources.append(f"profile:{profile}")
        defaults = _apply_layer(rules, defaults, prof, f"profile:{profile}", problems)

    if local_path is not None:
        local = _read_doc(local_path, "local", problems)
        if local is not None:
            sources.append("local")
            defaults = _apply_layer(rules, defaults, local, "local", problems)
            redact = local.get("redact", {})
            if isinstance(redact, Mapping):
                _unknown_keys(redact, ("extra_patterns",), "local.redact", problems)
                extra = _regex_list(
                    redact.get("extra_patterns", []), "local.redact.extra_patterns", problems
                )
                redact_patterns = tuple(extra or ())
            else:
                problems.append("local.redact: must be a table")

    if problems:
        raise PolicyError(problems)
    return Policy(
        profile=profile,
        rules=tuple(rules.values()),
        defaults=defaults,
        readonly_allowlist=allowlist,
        redact_patterns=redact_patterns,
        sources=tuple(sources),
    )


def project_profile(root: Path) -> str:
    """Profile named in <root>/.chatur/config.toml ([policy] profile), else the default."""
    config = root / ".chatur" / "config.toml"
    if not config.is_file():
        return DEFAULT_PROFILE
    try:
        data = tomllib.loads(config.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise PolicyError([f"{config}: invalid TOML: {exc}"]) from exc
    profile = data.get("policy", {}).get("profile", DEFAULT_PROFILE)
    if not isinstance(profile, str):
        raise PolicyError([f"{config}: [policy] profile must be a string"])
    return profile


def load_project_policy(root: Path, *, policy_dir: Path | Traversable | None = None) -> Policy:
    local = root / ".chatur" / "policy.local.toml"
    return load_policy(
        project_profile(root),
        local_path=local if local.is_file() else None,
        policy_dir=policy_dir,
    )
