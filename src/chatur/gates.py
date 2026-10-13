"""Human-approved SDLC phase gates (ADR-0008, ADR-0021). Stdlib-only, no network.

State lives in <root>/.chatur/state.json and is written only here. Approvals bind to a digest of the
phase's artifacts and to an anchor in the audit chain.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import subprocess
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from chatur import audit
from chatur.events import ChaturEvent, EventKind
from chatur.guard import glob_matches

SCHEMA = "chatur.state/v1"
PHASES = ("requirements", "design", "build", "test", "review", "release")
DEFAULT_ARTIFACTS: Mapping[str, tuple[str, ...]] = {
    "requirements": ("docs/requirements/**/*.md",),
    "design": ("docs/design/**/*.md", "docs/security/threat-model*.md"),
    "build": ("src/**", "tests/**"),
    "test": ("docs/test/**/*.md",),
    "review": ("docs/review/**/*.md",),
    "release": ("docs/releases/**/*.md", "CHANGELOG.md"),
}
AGENT_ENV_MARKERS = (
    "CLAUDECODE",
    "CLAUDE_CODE_ENTRYPOINT",
    "CHATUR_AGENT_SESSION",
    "COPILOT_AGENT_ID",
    "GITHUB_ACTIONS",
    "CI",
)
SKIP_DIRS = frozenset(
    {".git", ".chatur", ".venv", "venv", "node_modules", "__pycache__", "dist", "build"}
)
MAX_LISTED_FILES = 100

MAX_PREVIEW_FILES = 10


@dataclass(frozen=True, slots=True)
class ConfirmRequest:
    """Everything the human sees before typing the confirmation."""

    action: str  # "approve" | "revoke"
    phase: str
    approver: str
    details: tuple[str, ...]  # human-readable lines (artifacts, affected gates, ...)


Confirm = Callable[[ConfirmRequest], bool]


class GateError(RuntimeError):
    pass


# --------------------------------------------------------------------------- state


def state_path(root: Path) -> Path:
    return root / ".chatur" / "state.json"


def load_state(root: Path) -> dict[str, Any]:
    path = state_path(root)
    if not path.is_file():
        return {"schema": SCHEMA, "gates": {}}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GateError(f"{path}: invalid JSON ({exc})") from exc
    if not isinstance(state, dict) or state.get("schema") != SCHEMA:
        raise GateError(f"{path}: expected schema {SCHEMA!r}")
    if not isinstance(state.get("gates"), dict):
        raise GateError(f"{path}: 'gates' must be an object")
    return state


def save_state(root: Path, state: Mapping[str, Any]) -> None:
    """Atomic write: temp file in the same directory, then rename over the original."""
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def approved_gates(root: Path) -> frozenset[str]:
    """Recorded approvals for the hook path: no hashing (ADR-0012). Unreadable state -> none,
    which is the stricter outcome."""
    try:
        return frozenset(p for p in load_state(root)["gates"] if p in PHASES)
    except (GateError, OSError):
        return frozenset()


# --------------------------------------------------------------------------- artifacts


def artifact_globs(root: Path, phase: str) -> tuple[str, ...]:
    config = root / ".chatur" / "config.toml"
    if config.is_file():
        try:
            data = tomllib.loads(config.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise GateError(f"{config}: invalid TOML ({exc})") from exc
        override = data.get("gates", {}).get(phase, {}).get("artifacts")
        if override is not None:
            if not isinstance(override, list) or not all(isinstance(g, str) for g in override):
                raise GateError(f"{config}: [gates.{phase}] artifacts must be a list of strings")
            return tuple(override)
    return DEFAULT_ARTIFACTS[phase]


def is_init_placeholder(root: Path, rel: str) -> bool:
    """True for a docs/<phase-folder>/README.md still exactly as `chatur init` wrote it.
    Placeholders must not satisfy the "artifacts exist" gate check (walkthrough finding)."""
    from chatur.project import placeholder_readme  # local import: project -> adr -> gates

    parts = rel.split("/")
    if len(parts) != 3 or parts[0] != "docs" or parts[2] != "README.md":
        return False
    expected = placeholder_readme(parts[1])
    if expected is None:
        return False
    try:
        actual = (root / rel).read_text(encoding="utf-8").replace("\r\n", "\n")
    except (OSError, UnicodeDecodeError):
        return False
    return actual == expected


def collect_artifacts(root: Path, globs: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        for name in filenames:
            rel = name if rel_dir == "." else f"{rel_dir}/{name}"
            if any(glob_matches(rel, g) for g in globs) and not is_init_placeholder(root, rel):
                found.append(rel)
    return sorted(found)


def _content_for_digest(data: bytes) -> bytes:
    """Text files hash with LF line endings, so a gate approved on Windows (core.autocrlf -> CRLF)
    isn't stale on a Linux CI checkout (LF). Binary files (containing NUL) hash as-is."""
    return data if b"\0" in data else data.replace(b"\r\n", b"\n")


def artifact_digest(root: Path, files: list[str]) -> str:
    h = hashlib.sha256()
    for rel in files:
        content = _content_for_digest((root / rel).read_bytes())
        h.update(f"{rel}\0{hashlib.sha256(content).hexdigest()}\n".encode())
    return h.hexdigest()


# --------------------------------------------------------------------------- status


@dataclass(frozen=True, slots=True)
class GateStatus:
    phase: str
    state: str  # "approved" | "stale" | "pending"
    record: Mapping[str, Any] | None
    file_count: int
    digest: str


def status(root: Path) -> list[GateStatus]:
    gates = load_state(root)["gates"]
    result: list[GateStatus] = []
    for phase in PHASES:
        files = collect_artifacts(root, artifact_globs(root, phase))
        digest = artifact_digest(root, files)
        record = gates.get(phase)
        if record is None:
            state = "pending"
        elif record.get("artifacts", {}).get("digest") == digest:
            state = "approved"
        else:
            state = "stale"
        result.append(GateStatus(phase, state, record, len(files), digest))
    return result


def current_phase(statuses: list[GateStatus]) -> str | None:
    return next((s.phase for s in statuses if s.state != "approved"), None)


# --------------------------------------------------------------------------- human checks


def agent_markers(env: Mapping[str, str]) -> list[str]:
    return [k for k in AGENT_ENV_MARKERS if env.get(k)]


def _human_checks(phase: str, action: str, env: Mapping[str, str], interactive: bool) -> None:
    """Who may act (a human at a terminal). The typed confirmation comes last, after every
    other check has passed, so the human is never asked to confirm something that will fail."""
    if phase not in PHASES:
        raise GateError(f"unknown phase {phase!r} (phases: {', '.join(PHASES)})")
    markers = agent_markers(env)
    if markers:
        raise GateError(
            f"refusing to {action} a gate: agent/CI session detected ({', '.join(markers)}). "
            "A human must run this in their own terminal (ADR-0008)."
        )
    if not interactive:
        raise GateError(f"refusing to {action} a gate: an interactive terminal is required")


def _confirmed(confirm: Confirm, request: ConfirmRequest) -> None:
    if not confirm(request):
        raise GateError(f"not confirmed; the {request.phase!r} gate was not changed")


def _file_lines(files: list[str]) -> tuple[str, ...]:
    shown = [f"  - {f}" for f in files[:MAX_PREVIEW_FILES]]
    if len(files) > MAX_PREVIEW_FILES:
        shown.append(f"  ... and {len(files) - MAX_PREVIEW_FILES} more")
    return (f"Artifacts ({len(files)} file{'s' if len(files) != 1 else ''}):", *shown)


def identity(root: Path) -> str:
    def git_config(key: str) -> str:
        try:
            result = subprocess.run(  # noqa: S603 - fixed argv, no shell
                ["git", "config", "--get", key],  # noqa: S607 - git resolved from PATH by design
                cwd=root,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        return result.stdout.strip()

    name, email = git_config("user.name"), git_config("user.email")
    if name and email:
        return f"{name} <{email}>"
    return name or email or getpass.getuser()


def _utc(clock: Callable[[], datetime] | None) -> str:
    now = (clock or (lambda: datetime.now(UTC)))().astimezone(UTC)
    return now.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _audit_event(root: Path, raw: dict[str, Any]) -> ChaturEvent:
    return ChaturEvent(
        kind=EventKind.GATE, assistant="human", session_id="chatur-cli", cwd=str(root), raw=raw
    )


# --------------------------------------------------------------------------- approve / revoke


def approve(
    root: Path,
    phase: str,
    *,
    env: Mapping[str, str],
    interactive: bool,
    confirm: Confirm,
    note: str | None = None,
    who: str | None = None,
    clock: Callable[[], datetime] | None = None,
    extra_patterns: tuple[str, ...] = (),
) -> dict[str, Any]:
    _human_checks(phase, "approve", env, interactive)
    state = load_state(root)
    statuses = {s.phase: s for s in status(root)}
    for earlier in PHASES[: PHASES.index(phase)]:
        if statuses[earlier].state != "approved":
            raise GateError(
                f"cannot approve {phase!r}: earlier gate {earlier!r} is {statuses[earlier].state}"
            )
    if statuses[phase].state == "approved":
        raise GateError(f"{phase!r} is already approved and unchanged; nothing to do")

    globs = artifact_globs(root, phase)
    files = collect_artifacts(root, globs)
    if not files:
        raise GateError(f"no artifacts for {phase!r}: expected files matching {list(globs)}")

    report = audit.verify(root)
    if not report.ok:
        raise GateError("audit log failed verification; run `chatur audit verify` first")
    anchor = {"seq": report.records, "hash": report.last_hash}

    who = who or identity(root)
    details = _file_lines(files)
    if statuses[phase].state == "stale":
        details = ("Re-approval: these artifacts changed since the last approval.", *details)
    _confirmed(confirm, ConfirmRequest("approve", phase, who, details))
    record: dict[str, Any] = {
        "approved_by": who,
        "approved_at": _utc(clock),
        "os_user": getpass.getuser(),
        "artifacts": {
            "digest": artifact_digest(root, files),
            "file_count": len(files),
            **({"files": files} if len(files) <= MAX_LISTED_FILES else {}),
        },
        "audit_anchor": anchor,
    }
    if note:
        record["note"] = note

    # Audit first: if the state write then fails, the log still shows the attempt.
    audit.AuditLog(root, extra_patterns=extra_patterns).append(
        _audit_event(root, {"action": "approve", "phase": phase, **record})
    )
    state["gates"][phase] = record
    save_state(root, state)
    return record


def revoke(
    root: Path,
    phase: str,
    *,
    env: Mapping[str, str],
    interactive: bool,
    confirm: Confirm,
    who: str | None = None,
    clock: Callable[[], datetime] | None = None,
    extra_patterns: tuple[str, ...] = (),
) -> list[str]:
    """Remove `phase` and every later gate. Returns the phases removed."""
    _human_checks(phase, "revoke", env, interactive)
    state = load_state(root)
    later = PHASES[PHASES.index(phase) :]
    removed = [p for p in later if p in state["gates"]]
    if not removed:
        raise GateError(f"{phase!r} is not approved; nothing to revoke")
    who = who or identity(root)
    _confirmed(
        confirm,
        ConfirmRequest(
            "revoke", phase, who, (f"Gates that will be revoked: {', '.join(removed)}",)
        ),
    )
    audit.AuditLog(root, extra_patterns=extra_patterns).append(
        _audit_event(
            root,
            {
                "action": "revoke",
                "phases": removed,
                "revoked_by": who,
                "revoked_at": _utc(clock),
            },
        )
    )
    for p in removed:
        del state["gates"][p]
    save_state(root, state)
    return removed


# --------------------------------------------------------------------------- verify (git/CI)


def verify_gates(root: Path) -> list[str]:
    """Problems for CI/pre-commit: stale gates, out-of-order approvals, anchors missing from the
    audit chain (detects audit tail truncation, ADR-0019)."""
    problems: list[str] = []
    try:
        statuses = status(root)
    except GateError as exc:
        return [str(exc)]
    seen_gap = None
    for s in statuses:
        if s.state == "pending":
            seen_gap = seen_gap or s.phase
            continue
        if seen_gap:
            problems.append(f"{s.phase}: approved although earlier gate {seen_gap!r} is not")
        if s.state == "stale":
            problems.append(f"{s.phase}: stale (artifacts changed since approval)")

    anchors = {
        s.phase: s.record["audit_anchor"]
        for s in statuses
        if s.record and isinstance(s.record.get("audit_anchor"), dict)
    }
    try:
        chain = {(r.get("seq"), r.get("hash")) for _, _, r in audit.iter_records(root)}
    except audit.AuditError as exc:
        return [*problems, f"audit log unreadable: {exc}"]
    for phase, anchor in anchors.items():
        key = (anchor.get("seq"), anchor.get("hash"))
        if key == (0, audit.GENESIS):
            continue
        if key not in chain:
            problems.append(
                f"{phase}: audit anchor seq {anchor.get('seq')} not found in the audit log "
                "(records were removed or rewritten)"
            )
    for s in statuses:
        if s.record and "audit_anchor" not in s.record:
            problems.append(f"{s.phase}: approval has no audit anchor")
    return problems
