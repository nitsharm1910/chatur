"""Install Chatur's distributable primitives without APM (ADR-0028). Stdlib-only.

Assistant-specific path mapping lives in the adapters; this module locates the primitives and
applies a list of files to a project with an ownership manifest (never clobbering user edits).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from chatur import __version__

MANIFEST_SCHEMA = "chatur.primitives/v1"


class PrimitivesError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PrimitiveFile:
    target: str  # project-relative POSIX path
    content: bytes


@dataclass
class InstallReport:
    written: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (path, reason)


def primitives_root() -> Path:
    """`chatur/_primitives` in an installed wheel, else the repo's `.apm/` (editable checkout)."""
    packaged = resources.files("chatur").joinpath("_primitives")
    if packaged.is_dir():
        return Path(str(packaged))
    source = Path(__file__).resolve().parents[2] / ".apm"
    if source.is_dir():
        return source
    raise PrimitivesError("Chatur primitives not found; reinstall chatur or use `apm install`")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_manifest(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PrimitivesError(f"{path} is not valid JSON ({exc})") from exc
    if data.get("schema") != MANIFEST_SCHEMA or not isinstance(data.get("files"), dict):
        raise PrimitivesError(f"{path}: unexpected manifest format")
    return dict(data["files"])


def _save_manifest(path: Path, files: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "schema": MANIFEST_SCHEMA,
        "chatur_version": __version__,
        "files": dict(sorted(files.items())),
    }
    path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")


def _prune_empty_dirs(root: Path, rel_paths: Iterable[str]) -> None:
    for rel in rel_paths:
        parent = (root / rel).parent
        while parent != root and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent


def apply(
    root: Path, files: list[PrimitiveFile], manifest_rel: str, *, force: bool
) -> InstallReport:
    report = InstallReport()
    manifest_path = root / manifest_rel
    old = _load_manifest(manifest_path)
    new: dict[str, str] = {}

    for item in files:
        path = root / item.target
        wanted = _sha(item.content)
        if path.exists():
            current = _sha(path.read_bytes())
            ours_unmodified = old.get(item.target) == current
            if current == wanted:
                if item.target in old or force:
                    report.unchanged.append(item.target)
                    new[item.target] = wanted
                else:
                    report.skipped.append((item.target, "identical file not created by chatur"))
                continue
            if not ours_unmodified and not force:
                reason = "modified locally" if item.target in old else "not created by chatur"
                report.skipped.append((item.target, f"{reason}; use --force to overwrite"))
                if item.target in old:
                    new[item.target] = old[item.target]  # still ours, keep tracking
                continue
            report.updated.append(item.target)
        else:
            report.written.append(item.target)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(item.content)
        new[item.target] = wanted

    shipped = {f.target for f in files}
    for rel, digest in old.items():
        if rel in shipped:
            continue
        path = root / rel
        if path.is_file() and _sha(path.read_bytes()) == digest:
            path.unlink()
            report.removed.append(rel)
        elif path.is_file():
            report.skipped.append((rel, "no longer shipped but modified locally; left in place"))
    _prune_empty_dirs(root, report.removed)
    _save_manifest(manifest_path, new)
    return report


def remove(root: Path, manifest_rel: str) -> InstallReport:
    report = InstallReport()
    manifest_path = root / manifest_rel
    old = _load_manifest(manifest_path)
    for rel, digest in old.items():
        path = root / rel
        if not path.is_file():
            continue
        if _sha(path.read_bytes()) == digest:
            path.unlink()
            report.removed.append(rel)
        else:
            report.skipped.append((rel, "modified locally; left in place"))
    _prune_empty_dirs(root, report.removed)
    if manifest_path.is_file():
        manifest_path.unlink()
    return report
