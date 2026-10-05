"""Architecture Decision Records: create from a template and list them (ADR-0001, ADR-0022).

Stdlib-only. New ADRs are always `Proposed`; only humans accept them (ADR-0001).
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from importlib import resources
from pathlib import Path

from chatur.gates import PHASES, identity

PHASE_CHOICES = (*PHASES, "meta")
_ADR_FILE = re.compile(r"^(\d{4})-[A-Za-z0-9._-]+\.md$")
_FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_TRAILING_COMMENT = re.compile(r"\s+#.*$")


class AdrError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AdrInfo:
    number: int
    id: str
    title: str
    status: str
    date: str
    path: Path


def decisions_dir(root: Path) -> Path:
    return root / "docs" / "decisions"


def packaged_template() -> str:
    return resources.files("chatur").joinpath("templates", "adr.md").read_text(encoding="utf-8")


def template_text(root: Path) -> str:
    project_template = decisions_dir(root) / "0000-template.md"
    if project_template.is_file():
        return project_template.read_text(encoding="utf-8")
    return packaged_template()


def slugify(title: str) -> str:
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")[:60].rstrip("-")
    if not slug:
        raise AdrError(f"title {title!r} produces an empty file name; use letters or digits")
    return slug


def _adr_files(directory: Path) -> list[tuple[int, Path]]:
    if not directory.is_dir():
        return []
    found = []
    for path in directory.iterdir():
        match = _ADR_FILE.match(path.name)
        if match and path.is_file() and int(match.group(1)) > 0:
            found.append((int(match.group(1)), path))
    return sorted(found)


def next_number(directory: Path) -> int:
    files = _adr_files(directory)
    return files[-1][0] + 1 if files else 1


def _yaml_scalar(value: str) -> str:
    """Quote when plain YAML would misread the value (colons, leading specials, comments)."""
    if re.search(r":\s|\s#|^[\s\-?:,\[\]{}#&*!|>'\"%@`]", value) or value != value.strip():
        return json.dumps(value, ensure_ascii=False)
    return value


def _set_front_matter(text: str, values: dict[str, str]) -> str:
    match = _FRONT_MATTER.match(text)
    if not match:
        raise AdrError("ADR template has no front matter (--- ... ---)")
    lines = match.group(1).split("\n")
    for key, value in values.items():
        line = f"{key}: {value}"
        for i, existing in enumerate(lines):
            if re.match(rf"^{re.escape(key)}\s*:", existing):
                lines[i] = line
                break
        else:
            lines.append(line)
    return "---\n" + "\n".join(lines) + "\n---\n" + text[match.end() :]


def parse_ref(ref: str | int) -> int:
    """'7', '0007', 'ADR-0007', 'adr-7' -> 7."""
    match = re.fullmatch(r"(?:adr-?)?0*(\d{1,4})", str(ref).strip(), re.IGNORECASE)
    if not match or int(match.group(1)) == 0:
        raise AdrError(f"invalid ADR reference {ref!r} (use e.g. 7, 0007, or ADR-0007)")
    return int(match.group(1))


def find_adr(root: Path, ref: str | int) -> Path:
    number = parse_ref(ref)
    for n, path in _adr_files(decisions_dir(root)):
        if n == number:
            return path
    raise AdrError(f"ADR-{number:04d} not found in {decisions_dir(root)}")


def _list_field(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.strip("[]").split(",") if v.strip()]


def _insert_after_heading(text: str, line: str) -> str:
    match = re.search(r"(?m)^# .*$", text)
    if not match:
        return text + f"\n{line}\n"
    return text[: match.end()] + f"\n\n{line}" + text[match.end() :]


def _write(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def new_adr(
    root: Path,
    title: str,
    *,
    phase: str = "design",
    tags: Sequence[str] = (),
    deciders: str | None = None,
    today: date | None = None,
    supersedes: Sequence[str | int] = (),
) -> Path:
    title = title.strip()
    if not title:
        raise AdrError("title is required")
    if phase not in PHASE_CHOICES:
        raise AdrError(f"unknown phase {phase!r} (choices: {', '.join(PHASE_CHOICES)})")
    replaced = [find_adr(root, ref) for ref in supersedes]  # validate before writing
    directory = decisions_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    number = next_number(directory)
    adr_id = f"ADR-{number:04d}"
    path = directory / f"{number:04d}-{slugify(title)}.md"
    if path.exists():
        raise AdrError(f"{path} already exists")

    text = template_text(root).replace("\r\n", "\n")
    text = _set_front_matter(
        text,
        {
            "id": adr_id,
            "title": _yaml_scalar(title),
            "status": "Proposed",
            "date": (today or date.today()).isoformat(),
            "deciders": _yaml_scalar(deciders or identity(root)),
            "phase": phase,
            "tags": "[" + ", ".join(t.strip() for t in tags if t.strip()) + "]",
        },
    )
    text, count = re.subn(r"(?m)^# ADR-[^\n]*$", f"# {adr_id}: {title}", text, count=1)
    if not count:
        text = text.replace("\n---\n", f"\n---\n\n# {adr_id}: {title}\n", 1)
    if replaced:
        ids = [f"ADR-{int(p.name[:4]):04d}" for p in replaced]
        text = _set_front_matter(text, {"supersedes": "[" + ", ".join(ids) + "]"})
        links = ", ".join(f"[{i}]({p.name})" for i, p in zip(ids, replaced, strict=True))
        text = _insert_after_heading(text, f"> Supersedes {links}.")
    _write(path, text)
    return path


def supersede(root: Path, old_ref: str | int, new_ref: str | int) -> tuple[Path, Path]:
    """Mark `old` superseded by `new` (which must already be Accepted, ADR-0001/ADR-0024)."""
    old_path, new_path = find_adr(root, old_ref), find_adr(root, new_ref)
    if old_path == new_path:
        raise AdrError("an ADR cannot supersede itself")
    old_id, new_id = f"ADR-{int(old_path.name[:4]):04d}", f"ADR-{int(new_path.name[:4]):04d}"
    old_text = old_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    new_text = new_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    old_fields, new_fields = parse_front_matter(old_text), parse_front_matter(new_text)

    if new_fields.get("status", "").lower() != "accepted":
        raise AdrError(
            f"{new_id} is {new_fields.get('status', 'unknown')!r}; a human must accept it "
            "before it can supersede another ADR (ADR-0001)"
        )
    if old_fields.get("status", "").lower().startswith("superseded"):
        raise AdrError(f"{old_id} is already {old_fields['status']!r}")

    old_text = _set_front_matter(
        old_text, {"status": f"Superseded by {new_id}", "superseded_by": new_id}
    )
    old_text = _insert_after_heading(old_text, f"> **Superseded by [{new_id}]({new_path.name}).**")
    existing = _list_field(new_fields.get("supersedes"))
    if old_id not in existing:
        new_text = _set_front_matter(
            new_text, {"supersedes": "[" + ", ".join([*existing, old_id]) + "]"}
        )
    _write(old_path, old_text)
    _write(new_path, new_text)
    return old_path, new_path


def parse_front_matter(text: str) -> dict[str, str]:
    match = _FRONT_MATTER.match(text.replace("\r\n", "\n"))
    if not match:
        return {}
    fields: dict[str, str] = {}
    for line in match.group(1).split("\n"):
        key, sep, value = line.partition(":")
        if not sep or not key.strip() or line.startswith((" ", "\t", "#")):
            continue
        value = value.strip()
        if value.startswith('"'):
            try:
                value = json.loads(value[: value.rindex('"') + 1])
            except (ValueError, json.JSONDecodeError):
                value = value.strip('"')
        elif value.startswith("'"):
            value = value[1 : value.rindex("'")] if value.count("'") >= 2 else value.strip("'")
        else:
            value = _TRAILING_COMMENT.sub("", value)
        fields[key.strip()] = value
    return fields


def list_adrs(root: Path, *, status: str | None = None) -> list[AdrInfo]:
    result = []
    for number, path in _adr_files(decisions_dir(root)):
        fields = parse_front_matter(path.read_text(encoding="utf-8"))
        info = AdrInfo(
            number=number,
            id=fields.get("id", f"ADR-{number:04d}"),
            title=fields.get("title", path.stem),
            status=fields.get("status", "unknown"),
            date=fields.get("date", ""),
            path=path,
        )
        if status is None or info.status.lower().startswith(status.lower()):
            result.append(info)
    return result
