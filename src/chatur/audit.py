"""Append-only, hash-chained, redacted audit log (ADR-0006, ADR-0015, ADR-0019).

Stdlib-only (ADR-0012). One file per UTC day under <root>/.chatur/audit/, one chain across files.
Appends are serialised across processes with an OS file lock.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from chatur import __version__
from chatur.events import ChaturEvent
from chatur.redact import redact
from chatur.verdict import Verdict

SCHEMA = "chatur.audit/v1"
GENESIS = "0" * 64
LOCK_TIMEOUT_S = 2.0
_DAY_FILE = re.compile(r"^\d{4}-\d{2}-\d{2}\.jsonl$")


class AuditError(RuntimeError):
    pass


def audit_dir(root: Path) -> Path:
    return root / ".chatur" / "audit"


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def record_hash(record: dict[str, Any]) -> str:
    body = {k: v for k, v in record.items() if k != "hash"}
    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()


def day_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.iterdir() if p.is_file() and _DAY_FILE.match(p.name))


# --------------------------------------------------------------------------- locking

if os.name == "nt":
    import msvcrt

    def _try_lock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)

    def _unlock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _try_lock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


@contextmanager
def _exclusive(lock_path: Path, timeout: float) -> Iterator[None]:
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                _try_lock(fd)
                break
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise AuditError(f"timed out after {timeout}s waiting for {lock_path}") from exc
                time.sleep(0.005)
        try:
            yield
        finally:
            _unlock(fd)
    finally:
        os.close(fd)


# --------------------------------------------------------------------------- reading


def _last_line(path: Path) -> tuple[bytes | None, bool]:
    """(last line without newline, whether the file ends with a newline). Reads from the end."""
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        if size == 0:
            return None, True
        chunk = 8192
        while True:
            start = max(0, size - chunk)
            f.seek(start)
            data = f.read(size - start)
            complete = data.endswith(b"\n")
            body = data[:-1] if complete else data
            if b"\n" in body or start == 0:
                return body.rsplit(b"\n", 1)[-1], complete
            chunk *= 4


def _parse(line: bytes | str, where: str) -> dict[str, Any]:
    try:
        record = json.loads(line)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AuditError(f"{where}: not valid JSON ({exc})") from exc
    if not isinstance(record, dict):
        raise AuditError(f"{where}: record is not an object")
    return record


def _tail_record(directory: Path) -> dict[str, Any] | None:
    """Last record of the newest non-empty day file, verified against its own hash."""
    for path in reversed(day_files(directory)):
        line, complete = _last_line(path)
        if line is None or not line.strip():
            continue
        if not complete:
            raise AuditError(f"{path.name}: last line is incomplete; run `chatur audit verify`")
        record = _parse(line, path.name)
        if record.get("hash") != record_hash(record):
            raise AuditError(f"{path.name}: last record fails its hash; run `chatur audit verify`")
        return record
    return None


def iter_records(root: Path) -> Iterator[tuple[Path, int, dict[str, Any]]]:
    """Yield (file, line number, record) in chain order. Raises AuditError on unparseable lines."""
    for path in day_files(audit_dir(root)):
        with path.open("rb") as f:
            for number, line in enumerate(f, start=1):
                if line.strip():
                    yield path, number, _parse(line, f"{path.name}:{number}")


# --------------------------------------------------------------------------- writing

_PATH_KEYS = frozenset({"file_path", "notebook_path", "path", "paths"})


def _digest(value: Any) -> Any:
    if isinstance(value, str):
        return {"sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(), "chars": len(value)}
    if isinstance(value, dict):
        return {k: (v if k in _PATH_KEYS else _digest(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_digest(v) for v in value]
    return value


def strip_file_contents(event: dict[str, Any]) -> dict[str, Any]:
    """ADR-0006/ADR-0025: file-write events keep paths; content becomes {sha256, chars}."""
    tool = event.get("tool")
    if isinstance(tool, dict) and tool.get("category") == "file_write":
        tool["args"] = {
            k: (v if k in _PATH_KEYS else _digest(v)) for k, v in (tool.get("args") or {}).items()
        }
    return event


class AuditLog:
    def __init__(
        self,
        root: Path,
        *,
        extra_patterns: Sequence[str] = (),
        clock: Callable[[], datetime] | None = None,
        lock_timeout: float = LOCK_TIMEOUT_S,
    ) -> None:
        self.root = root
        self.directory = audit_dir(root)
        self.extra_patterns = tuple(extra_patterns)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock_timeout = lock_timeout

    def append(self, event: ChaturEvent, verdict: Verdict | None = None) -> dict[str, Any]:
        """Redact, chain, and append one record. Returns the record as written."""
        self.directory.mkdir(parents=True, exist_ok=True)
        now = self._clock().astimezone(UTC)
        with _exclusive(self.directory / ".lock", self._lock_timeout):
            previous = _tail_record(self.directory)
            record: dict[str, Any] = redact(
                {
                    "schema": SCHEMA,
                    "seq": (previous["seq"] + 1) if previous else 1,
                    "ts": now.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                    "chatur_version": __version__,
                    "event": strip_file_contents(event.to_dict(redact_secrets=False)),
                    "verdict": verdict.to_dict() if verdict else None,
                    "prev": previous["hash"] if previous else GENESIS,
                },
                self.extra_patterns,
            )
            record["hash"] = record_hash(record)
            path = self.directory / f"{now:%Y-%m-%d}.jsonl"
            with path.open("ab") as f:
                f.write((canonical(record) + "\n").encode("utf-8"))
                f.flush()
                os.fsync(f.fileno())
        return record


# --------------------------------------------------------------------------- verification


@dataclass
class AuditReport:
    records: int = 0
    files: int = 0
    problems: list[str] = field(default_factory=list)
    last_hash: str = GENESIS

    @property
    def ok(self) -> bool:
        return not self.problems


def verify(root: Path) -> AuditReport:
    """Walk every record in chain order and report all integrity problems."""
    report = AuditReport()
    expected_prev: str | None = GENESIS  # None = unknown after an unparseable line
    expected_seq = 1
    for path in day_files(audit_dir(root)):
        report.files += 1
        data = path.read_bytes()
        if data and not data.endswith(b"\n"):
            report.problems.append(f"{path.name}: last line is incomplete (truncated write?)")
        for number, line in enumerate(data.splitlines(), start=1):
            where = f"{path.name}:{number}"
            if not line.strip():
                report.problems.append(f"{where}: blank line")
                continue
            try:
                record = _parse(line, where)
            except AuditError as exc:
                report.problems.append(str(exc))
                expected_prev = None
                continue
            report.records += 1
            if record.get("schema") != SCHEMA:
                report.problems.append(f"{where}: unknown schema {record.get('schema')!r}")
            if record.get("hash") != record_hash(record):
                report.problems.append(f"{where}: hash mismatch (record was modified)")
            if expected_prev is not None and record.get("prev") != expected_prev:
                report.problems.append(
                    f"{where}: chain broken (prev does not match the preceding record; "
                    "a record was removed, inserted, or reordered, or an earlier file is missing)"
                )
            if record.get("seq") != expected_seq:
                report.problems.append(
                    f"{where}: seq {record.get('seq')} (expected {expected_seq})"
                )
            expected_prev = record.get("hash")
            expected_seq = (record.get("seq") or expected_seq) + 1
    report.last_hash = expected_prev or ""
    return report


def tail(root: Path, n: int = 20) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in reversed(day_files(audit_dir(root))):
        lines = [ln for ln in path.read_bytes().splitlines() if ln.strip()]
        for line in reversed(lines):
            records.append(_parse(line, path.name))
            if len(records) >= n:
                return list(reversed(records))
    return list(reversed(records))


def summarize(record: dict[str, Any]) -> str:
    event = record.get("event") or {}
    tool = event.get("tool") or {}
    verdict = record.get("verdict") or {}
    what = tool.get("command") or ", ".join(tool.get("paths") or []) or tool.get("name") or ""
    return (
        f"#{record.get('seq')} {record.get('ts')} {event.get('assistant')} {event.get('kind')}"
        f" {verdict.get('decision', '-'):<5} {what}"
    ).rstrip()
