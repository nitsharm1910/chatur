"""Run the hook path in a bare interpreter (`python -I -S`: no site-packages, no user env).

argv: <src dir> <project root>. Prints one JSON line. Used by tests/test_hook_budget.py (ADR-0012).
"""
# ruff: noqa: E402 - imports must follow the sys.path setup

import json
import sys
import time

started = time.perf_counter()
sys.path.insert(0, sys.argv[1])

from pathlib import Path

import chatur.cli  # noqa: F401 - the whole CLI (future hook entrypoint) must import bare
from chatur.audit import AuditLog
from chatur.events import ChaturEvent, EventKind, ToolCall, ToolCategory
from chatur.gates import approved_gates
from chatur.guard import GuardContext, evaluate
from chatur.policy import load_project_policy

root = Path(sys.argv[2])
policy = load_project_policy(root)
command = "pwsh -NoProfile -c 'cd src; git status; pytest -q 2>&1 | tee out.log'"
event = ChaturEvent(
    kind=EventKind.PRE_TOOL,
    assistant="bench",
    session_id="bench",
    cwd=str(root),
    tool=ToolCall(ToolCategory.SHELL, "Bash", {"command": command}, command=command),
)
verdict = evaluate(event, policy, GuardContext(approved_gates=approved_gates(root)))
AuditLog(root, extra_patterns=policy.redact_patterns).append(event, verdict)

stdlib = set(sys.stdlib_module_names)
third_party = sorted(
    {name.split(".")[0] for name in sys.modules}
    - stdlib
    - {"chatur", "__main__"}
    - {n for n in sys.modules if n.startswith("_")}
)
print(
    json.dumps(
        {
            "elapsed_ms": (time.perf_counter() - started) * 1000,
            "decision": verdict.decision.value,
            "third_party": third_party,
            "site_loaded": "site" in sys.modules,
        }
    )
)
