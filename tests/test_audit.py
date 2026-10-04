"""Audit log: redaction, chain, tampering, cross-day, concurrency (ADR-0006/0015/0019)."""

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path

import pytest

from chatur.audit import GENESIS, AuditError, AuditLog, audit_dir, tail, verify
from chatur.cli import main
from chatur.events import ChaturEvent, EventKind
from chatur.verdict import Decision, RuleHit, Verdict
from conftest import shell_event

TOKEN = "ghp_" + "a" * 36
DAY1 = datetime(2026, 10, 3, 23, 59, tzinfo=UTC)


def _clock(*times: datetime):
    it = iter(times)
    last = [times[-1]]

    def now() -> datetime:
        last[0] = next(it, last[0])
        return last[0]

    return now


def _write(root: Path, n: int = 3, clock=None) -> AuditLog:
    log = AuditLog(root, clock=clock)
    for i in range(n):
        log.append(shell_event(f"echo {i}"), Verdict.from_hits([RuleHit("r", Decision.ASK, "x")]))
    return log


def _lines(root: Path, name: str | None = None) -> tuple[Path, list[str]]:
    files = sorted(audit_dir(root).glob("*.jsonl"))
    path = files[0] if name is None else audit_dir(root) / name
    return path, path.read_text(encoding="utf-8").splitlines()


def _save(path: Path, lines: list[str]) -> None:
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")


# --------------------------------------------------------------------------- writing


def test_append_creates_valid_chain(tmp_path):
    _write(tmp_path, 5)
    report = verify(tmp_path)
    assert report.ok, report.problems
    assert report.records == 5
    records = tail(tmp_path, 10)
    assert [r["seq"] for r in records] == [1, 2, 3, 4, 5]
    assert records[0]["prev"] == GENESIS
    assert all(b["prev"] == a["hash"] for a, b in pairwise(records))


def test_record_contents(tmp_path):
    record = AuditLog(tmp_path).append(shell_event("git status"), None)
    assert record["schema"] == "chatur.audit/v1"
    assert record["event"]["tool"]["command"] == "git status"
    assert record["verdict"] is None
    assert record["chatur_version"]


def test_secrets_masked_everywhere(tmp_path):
    verdict = Verdict.from_hits([RuleHit("r", Decision.ASK, f"command had {TOKEN}")])
    AuditLog(tmp_path).append(shell_event(f"git clone https://{TOKEN}@github.com/a/b"), verdict)
    raw = next(audit_dir(tmp_path).glob("*.jsonl")).read_text(encoding="utf-8")
    assert TOKEN not in raw
    assert "[REDACTED:github_token]" in raw
    assert verify(tmp_path).ok


def test_extra_patterns_masked(tmp_path):
    event = ChaturEvent(
        kind=EventKind.PROMPT,
        assistant="t",
        session_id="s",
        cwd=".",
        prompt="ticket ACME-12345678 contains customer data",
    )
    AuditLog(tmp_path, extra_patterns=[r"\bACME-\d{8}\b"]).append(event)
    raw = next(audit_dir(tmp_path).glob("*.jsonl")).read_text(encoding="utf-8")
    assert "ACME-12345678" not in raw and "[REDACTED:custom]" in raw


def test_lines_are_canonical_json(tmp_path):
    _write(tmp_path, 1)
    _, (line,) = _lines(tmp_path)
    record = json.loads(line)
    assert line == json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# --------------------------------------------------------------------------- tampering


def test_modified_record_detected(tmp_path):
    _write(tmp_path, 3)
    path, lines = _lines(tmp_path)
    lines[1] = lines[1].replace('"decision":"ask"', '"decision":"allow"')
    _save(path, lines)
    report = verify(tmp_path)
    assert not report.ok
    assert any(":2: hash mismatch" in p for p in report.problems)


def test_deleted_record_detected(tmp_path):
    _write(tmp_path, 3)
    path, lines = _lines(tmp_path)
    del lines[1]
    _save(path, lines)
    problems = verify(tmp_path).problems
    assert any("chain broken" in p for p in problems)
    assert any("seq 3 (expected 2)" in p for p in problems)


def test_reordered_records_detected(tmp_path):
    _write(tmp_path, 3)
    path, lines = _lines(tmp_path)
    lines[0], lines[1] = lines[1], lines[0]
    _save(path, lines)
    assert any("chain broken" in p for p in verify(tmp_path).problems)


def test_forged_record_with_recomputed_hash_detected(tmp_path):
    from chatur.audit import canonical, record_hash

    _write(tmp_path, 3)
    path, lines = _lines(tmp_path)
    forged = json.loads(lines[1])
    forged["verdict"]["decision"] = "allow"
    forged["hash"] = record_hash(forged)  # attacker fixes this record's hash...
    lines[1] = canonical(forged)
    _save(path, lines)
    problems = verify(tmp_path).problems
    assert any(":3: chain broken" in p for p in problems)  # ...but the next record no longer links


def test_truncated_line_detected_and_blocks_append(tmp_path):
    _write(tmp_path, 2)
    path, _ = _lines(tmp_path)
    data = path.read_bytes()
    path.write_bytes(data[:-20])
    assert not verify(tmp_path).ok
    with pytest.raises(AuditError, match="incomplete"):
        AuditLog(tmp_path).append(shell_event("ls"))


def test_tampered_tail_blocks_append(tmp_path):
    _write(tmp_path, 2)
    path, lines = _lines(tmp_path)
    lines[-1] = lines[-1].replace('"echo 1"', '"echo X"')
    _save(path, lines)
    with pytest.raises(AuditError, match="fails its hash"):
        AuditLog(tmp_path).append(shell_event("ls"))


def test_garbage_line_reported(tmp_path):
    _write(tmp_path, 2)
    path, lines = _lines(tmp_path)
    lines.insert(1, "{not json")
    _save(path, lines)
    problems = verify(tmp_path).problems
    assert any("not valid JSON" in p for p in problems)


# --------------------------------------------------------------------------- days


def test_chain_spans_days(tmp_path):
    clock = _clock(DAY1, DAY1, DAY1 + timedelta(minutes=2), DAY1 + timedelta(minutes=3))
    _write(tmp_path, 4, clock)
    files = sorted(p.name for p in audit_dir(tmp_path).glob("*.jsonl"))
    assert files == ["2026-10-03.jsonl", "2026-10-04.jsonl"]
    _, day1 = _lines(tmp_path, "2026-10-03.jsonl")
    _, day2 = _lines(tmp_path, "2026-10-04.jsonl")
    assert json.loads(day2[0])["prev"] == json.loads(day1[-1])["hash"]
    assert json.loads(day2[0])["seq"] == 3
    report = verify(tmp_path)
    assert report.ok and report.files == 2 and report.records == 4


def test_missing_earlier_file_detected(tmp_path):
    clock = _clock(DAY1, DAY1 + timedelta(minutes=2))
    _write(tmp_path, 2, clock)
    (audit_dir(tmp_path) / "2026-10-03.jsonl").unlink()
    problems = verify(tmp_path).problems
    assert any("2026-10-04.jsonl:1: chain broken" in p for p in problems)


def test_non_day_files_ignored(tmp_path):
    _write(tmp_path, 1)
    (audit_dir(tmp_path) / "notes.txt").write_text("hi", encoding="utf-8")
    assert verify(tmp_path).ok


def test_empty_log_is_ok(tmp_path):
    report = verify(tmp_path)
    assert report.ok and report.records == 0


# --------------------------------------------------------------------------- concurrency


def test_concurrent_writers_from_separate_processes(tmp_path):
    helper = Path(__file__).with_name("_audit_writer.py")
    procs = [
        subprocess.Popen([sys.executable, str(helper), str(tmp_path), "15", f"w{i}"])
        for i in range(4)
    ]
    assert all(p.wait(timeout=120) == 0 for p in procs)
    report = verify(tmp_path)
    assert report.ok, report.problems
    assert report.records == 60


# --------------------------------------------------------------------------- CLI


def test_cli_verify_and_tail(tmp_path, capsys):
    _write(tmp_path, 3)
    assert main(["audit", "verify", "--root", str(tmp_path)]) == 0
    assert "audit OK: 3 records" in capsys.readouterr().out
    assert main(["audit", "tail", "--root", str(tmp_path), "-n", "2"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 2 and out[-1].startswith("#3 ")


def test_cli_verify_fails_on_tamper(tmp_path, capsys):
    _write(tmp_path, 2)
    path, lines = _lines(tmp_path)
    lines[0] = lines[0].replace("echo 0", "echo Z")
    _save(path, lines)
    assert main(["audit", "verify", "--root", str(tmp_path)]) == 1
    assert "hash mismatch" in capsys.readouterr().err
