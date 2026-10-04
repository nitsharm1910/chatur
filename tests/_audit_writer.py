"""Helper process for the concurrent-writer test: append N records to the audit log at ROOT."""

import sys
from pathlib import Path

from chatur.audit import AuditLog
from chatur.events import ChaturEvent, EventKind

root, count, worker = Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
log = AuditLog(root, lock_timeout=30)
for i in range(count):
    log.append(
        ChaturEvent(
            kind=EventKind.PROMPT, assistant=worker, session_id=worker, cwd=".", prompt=str(i)
        )
    )
