"""Hook entrypoint: native payload -> evaluate -> audit -> native output (ADR-0004, ADR-0025).

Stdlib-only, inside the 500 ms budget (ADR-0012). PreToolUse fails closed: any error denies.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from chatur.adapters import HookOutput, get_adapter
from chatur.audit import AuditLog
from chatur.events import ChaturEvent, EventKind
from chatur.gates import PHASES, approved_gates
from chatur.guard import GuardContext, evaluate
from chatur.policy import Policy, load_project_policy
from chatur.redact import redact

EVALUATED = frozenset(
    {EventKind.PRE_TOOL, EventKind.PROMPT, EventKind.STOP, EventKind.SUBAGENT_STOP}
)


def session_context(root: Path, policy: Policy) -> str:
    approved = approved_gates(root)
    phase = next((p for p in PHASES if p not in approved), "all gates approved")
    return (
        f"Chatur guardrails are active (profile: {policy.profile}; current SDLC phase: {phase}). "
        "You may not git commit/push, rewrite history, or merge/create PRs; a human does that. "
        "Every command and file change needs human approval. Never write secrets into files or "
        "commands. Never approve or revoke gates. Record significant decisions with "
        '`chatur adr new "<title>"`. Dry-run a command with `chatur check "<command>"`.'
    )


def _capture(env: Mapping[str, str], payload: Mapping[str, object], event_name: str) -> None:
    """Debug aid: CHATUR_CAPTURE_DIR saves redacted payloads as test fixtures."""
    directory = env.get("CHATUR_CAPTURE_DIR")
    if not directory:
        return
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    count = len(list(target.glob(f"{event_name}-*.json")))
    (target / f"{event_name}-{count + 1:03d}.json").write_text(
        json.dumps(redact(dict(payload)), indent=2, ensure_ascii=False), encoding="utf-8"
    )


def run_hook(
    adapter_name: str, stdin_text: str, env: Mapping[str, str], event_arg: str | None = None
) -> HookOutput:
    adapter = get_adapter(adapter_name)
    event_name = event_arg
    try:
        payload = json.loads(stdin_text)
        if not isinstance(payload, dict):
            raise ValueError("hook input is not a JSON object")
        native_name = payload.get("hook_event_name")
        if event_arg and native_name != event_arg:
            raise ValueError(f"hook registered for {event_arg} received {native_name!r}")
        event_name = native_name if isinstance(native_name, str) else event_arg
        event: ChaturEvent | None = adapter.parse(payload, env)
        if event is None:
            return HookOutput()
        _capture(env, payload, str(event_name))

        root = adapter.project_root(payload, env)
        policy = load_project_policy(root)
        verdict = None
        if event.kind in EVALUATED:
            ctx = GuardContext(approved_gates=approved_gates(root), project_root=str(root))
            verdict = evaluate(event, policy, ctx)
        AuditLog(root, extra_patterns=policy.redact_patterns).append(event, verdict)

        context = None
        if event.kind is EventKind.SESSION_START:
            adapter.on_session_start(env)
            context = session_context(root, policy)
        return adapter.render(event, verdict, payload, context=context)
    except Exception as exc:
        return adapter.failure(event_name, f"Chatur hook error: {type(exc).__name__}: {exc}")
