"""ADR-0012 guardrails: stdlib-only package and a < 500 ms hook path (p95, fresh process)."""

import ast
import json
import math
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

import pytest

from chatur.events import ChaturEvent, EventKind, ToolCall, ToolCategory
from chatur.guard import evaluate
from chatur.policy import load_policy
from chatur.project import init_project

SRC = Path(__file__).resolve().parents[1] / "src"
HELPER = Path(__file__).with_name("_hook_path.py")
BUDGET_MS = float(os.environ.get("CHATUR_LATENCY_BUDGET_MS", "500"))
STDLIB = set(sys.stdlib_module_names)


def p95(samples: list[float]) -> float:
    ordered = sorted(samples)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


# --------------------------------------------------------------------------- stdlib only


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


@pytest.mark.parametrize(
    "module", sorted(SRC.joinpath("chatur").rglob("*.py")), ids=lambda p: p.name
)
def test_module_imports_only_stdlib(module):
    foreign = sorted(_imports(module) - STDLIB - {"chatur"})
    assert not foreign, f"{module.name} imports non-stdlib modules: {foreign}"


@pytest.fixture(scope="module")
def project(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("budget")
    init_project(root)
    return root


def _run_bare(project: Path) -> tuple[float, dict]:
    started = time.perf_counter()
    result = subprocess.run(
        [sys.executable, "-I", "-S", str(HELPER), str(SRC), str(project)],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    wall_ms = (time.perf_counter() - started) * 1000
    return wall_ms, json.loads(result.stdout)


def test_hook_path_runs_without_site_packages(project):
    _, report = _run_bare(project)
    assert report["site_loaded"] is False
    assert report["third_party"] == []
    assert report["decision"] == "ask"


# --------------------------------------------------------------------------- latency


def test_hook_path_p95_under_budget_fresh_process(project):
    _run_bare(project)  # warm the OS file cache / .pyc compilation
    samples = [_run_bare(project)[0] for _ in range(10)]
    print(
        f"\nfresh-process hook path: median {statistics.median(samples):.0f} ms, "
        f"p95 {p95(samples):.0f} ms, budget {BUDGET_MS:.0f} ms"
    )
    assert p95(samples) < BUDGET_MS


def test_in_process_p95_under_budget():
    events = [
        ChaturEvent(
            kind=EventKind.PRE_TOOL,
            assistant="bench",
            session_id="bench",
            cwd="/r",
            tool=ToolCall(ToolCategory.SHELL, "Bash", {}, command=c),
        )
        for c in (
            "git status",
            "pwsh -NoProfile -c 'cd x; git push origin main --force'",
            "python -m pytest tests/ -q 2>&1 | tee out.log",
            "rm -rf .chatur && echo done",
        )
    ]
    samples = []
    for i in range(40):
        started = time.perf_counter()
        evaluate(events[i % len(events)], load_policy("strict"))
        samples.append((time.perf_counter() - started) * 1000)
    print(f"\nin-process load+evaluate: p95 {p95(samples):.1f} ms")
    assert p95(samples) < BUDGET_MS / 10  # generous headroom: real budget is spent on startup


def test_p95_helper():
    assert p95([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]) == 10
    assert p95(list(range(1, 101))) == 95
