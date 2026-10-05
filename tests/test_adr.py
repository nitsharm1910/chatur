"""`chatur adr new|list` (ADR-0001, ADR-0022)."""

import json
from datetime import date
from pathlib import Path

import pytest

from chatur.adr import (
    AdrError,
    list_adrs,
    new_adr,
    next_number,
    parse_front_matter,
    parse_ref,
    slugify,
    supersede,
)
from chatur.cli import main

REPO = Path(__file__).resolve().parents[1]
TODAY = date(2026, 10, 4)


def _new(root: Path, title: str, **kw) -> Path:
    return new_adr(root, title, deciders="Tester <t@x>", today=TODAY, **kw)


def test_first_adr_from_packaged_template(tmp_path):
    path = _new(tmp_path, "Use PostgreSQL for orders", phase="design", tags=["db", "storage"])
    assert path.name == "0001-use-postgresql-for-orders.md"
    text = path.read_text(encoding="utf-8")
    fields = parse_front_matter(text)
    assert fields["id"] == "ADR-0001"
    assert fields["title"] == "Use PostgreSQL for orders"
    assert fields["status"] == "Proposed"
    assert fields["date"] == "2026-10-04"
    assert fields["deciders"] == "Tester <t@x>"
    assert fields["phase"] == "design"
    assert fields["tags"] == "[db, storage]"
    assert "# ADR-0001: Use PostgreSQL for orders" in text
    assert "\r\n" not in text


def test_numbering_follows_highest_and_ignores_template(tmp_path):
    d = tmp_path / "docs" / "decisions"
    d.mkdir(parents=True)
    for name in ("0000-template.md", "0002-a.md", "0007-b.md", "README.md", "notes.md"):
        (d / name).write_text("---\nid: x\n---\n", encoding="utf-8")
    assert next_number(d) == 8
    assert _new(tmp_path, "Next").name == "0008-next.md"


def test_project_template_is_used(tmp_path):
    d = tmp_path / "docs" / "decisions"
    d.mkdir(parents=True)
    (d / "0000-template.md").write_text(
        "---\nid: ADR-NNNN\ntitle: t\nstatus: Accepted\nowner: team-x\n---\n"
        "\n# ADR-NNNN: t\n\nCUSTOM\n",
        encoding="utf-8",
    )
    text = _new(tmp_path, "Custom one").read_text(encoding="utf-8")
    fields = parse_front_matter(text)
    assert fields["status"] == "Proposed"  # never inherits Accepted
    assert fields["owner"] == "team-x"
    assert "CUSTOM" in text and "# ADR-0001: Custom one" in text


def test_titles_needing_quotes_round_trip(tmp_path):
    title = "`chatur check`: evaluate # one action"
    path = _new(tmp_path, title)
    assert parse_front_matter(path.read_text(encoding="utf-8"))["title"] == title
    assert list_adrs(tmp_path)[0].title == title


@pytest.mark.parametrize(
    ("title", "slug"),
    [
        ("Use PostgreSQL!", "use-postgresql"),
        ("  Café — naïve façade  ", "cafe-naive-facade"),
        ("x" * 100, "x" * 60),
        ("API v2: REST → gRPC", "api-v2-rest-grpc"),
    ],
)
def test_slugify(title, slug):
    assert slugify(title) == slug


@pytest.mark.parametrize("title", ["", "   ", "!!!", "日本語"])
def test_bad_titles(tmp_path, title):
    with pytest.raises(AdrError):
        _new(tmp_path, title)


def test_bad_phase(tmp_path):
    with pytest.raises(AdrError, match="unknown phase"):
        _new(tmp_path, "x", phase="deploy")


def test_list_and_filter(tmp_path):
    _new(tmp_path, "One")
    second = _new(tmp_path, "Two")
    second.write_text(
        second.read_text(encoding="utf-8").replace("status: Proposed", "status: Accepted"),
        encoding="utf-8",
    )
    assert [a.title for a in list_adrs(tmp_path)] == ["One", "Two"]
    assert [a.id for a in list_adrs(tmp_path, status="accepted")] == ["ADR-0002"]
    assert [a.id for a in list_adrs(tmp_path, status="Prop")] == ["ADR-0001"]


def test_lists_chatur_own_decisions():
    adrs = list_adrs(REPO)
    assert len(adrs) >= 22
    assert [a.number for a in adrs] == list(range(1, len(adrs) + 1))  # no gaps
    assert all(a.id == f"ADR-{a.number:04d}" for a in adrs)
    assert all(a.status in {"Accepted", "Proposed"} for a in adrs)
    by_id = {a.id: a for a in adrs}
    assert by_id["ADR-0020"].title == "`chatur check`: evaluate one action from the command line"


def test_cli_new_and_list(tmp_path, capsys):
    assert (
        main(
            [
                "adr",
                "new",
                "Adopt OpenTelemetry",
                "--root",
                str(tmp_path),
                "--phase",
                "build",
                "--tags",
                "obs",
            ]
        )
        == 0
    )
    assert capsys.readouterr().out.strip().endswith("0001-adopt-opentelemetry.md")
    assert main(["adr", "list", "--root", str(tmp_path)]) == 0
    assert "ADR-0001  Proposed    Adopt OpenTelemetry" in capsys.readouterr().out
    assert main(["adr", "list", "--root", str(tmp_path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["status"] == "Proposed"


# --------------------------------------------------------------------------- supersede (ADR-0024)


def _accept(path: Path) -> None:
    path.write_text(
        path.read_text(encoding="utf-8").replace("status: Proposed", "status: Accepted"),
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("ref", "n"), [("7", 7), ("0007", 7), ("ADR-0007", 7), ("adr-7", 7), (12, 12)]
)
def test_parse_ref(ref, n):
    assert parse_ref(ref) == n


@pytest.mark.parametrize("ref", ["0", "ADR-", "seven", "12345", "ADR-00x1"])
def test_parse_ref_invalid(ref):
    with pytest.raises(AdrError, match="invalid ADR reference"):
        parse_ref(ref)


def test_new_with_supersedes_links_and_validates(tmp_path):
    old = _new(tmp_path, "Use MySQL")
    new = _new(tmp_path, "Use PostgreSQL", supersedes=["1"])
    text = new.read_text(encoding="utf-8")
    assert parse_front_matter(text)["supersedes"] == "[ADR-0001]"
    assert f"> Supersedes [ADR-0001]({old.name})." in text
    with pytest.raises(AdrError, match="ADR-0009 not found"):
        _new(tmp_path, "Nope", supersedes=["9"])
    assert len(list_adrs(tmp_path)) == 2  # failed call wrote nothing


def test_supersede_full_flow(tmp_path):
    old = _new(tmp_path, "Use MySQL")
    _accept(old)
    new = _new(tmp_path, "Use PostgreSQL")
    with pytest.raises(AdrError, match="a human must accept it"):
        supersede(tmp_path, "1", "2")
    _accept(new)
    supersede(tmp_path, "ADR-0001", "2")
    old_text, new_text = old.read_text(encoding="utf-8"), new.read_text(encoding="utf-8")
    old_fields = parse_front_matter(old_text)
    assert old_fields["status"] == "Superseded by ADR-0002"
    assert old_fields["superseded_by"] == "ADR-0002"
    assert f"> **Superseded by [ADR-0002]({new.name}).**" in old_text
    assert "# ADR-0001: Use MySQL" in old_text  # body otherwise intact
    assert parse_front_matter(new_text)["supersedes"] == "[ADR-0001]"
    assert [a.id for a in list_adrs(tmp_path, status="superseded")] == ["ADR-0001"]


def test_supersede_keeps_existing_supersedes_list(tmp_path):
    for title in ("A", "B"):
        _accept(_new(tmp_path, title))
    replacement = _new(tmp_path, "C", supersedes=["1"])
    _accept(replacement)
    supersede(tmp_path, 2, 3)
    assert parse_front_matter(replacement.read_text(encoding="utf-8"))["supersedes"] == (
        "[ADR-0001, ADR-0002]"
    )


def test_supersede_refusals(tmp_path):
    a, b = _new(tmp_path, "A"), _new(tmp_path, "B")
    _accept(a)
    _accept(b)
    with pytest.raises(AdrError, match="cannot supersede itself"):
        supersede(tmp_path, 1, 1)
    supersede(tmp_path, 1, 2)
    with pytest.raises(AdrError, match="already 'Superseded by ADR-0002'"):
        supersede(tmp_path, 1, 2)
    with pytest.raises(AdrError, match="not found"):
        supersede(tmp_path, 5, 2)


def test_cli_supersede(tmp_path, capsys):
    _accept(_new(tmp_path, "Old"))
    main(["adr", "new", "Replacement", "--supersedes", "1", "--root", str(tmp_path)])
    capsys.readouterr()
    assert main(["adr", "supersede", "1", "--by", "2", "--root", str(tmp_path)]) == 1
    assert "must accept it" in capsys.readouterr().err
    _accept(next((tmp_path / "docs" / "decisions").glob("0002-*.md")))
    assert main(["adr", "supersede", "1", "--by", "2", "--root", str(tmp_path)]) == 0
    assert "superseded by 0002-replacement.md" in capsys.readouterr().out


def test_cli_new_error(tmp_path, capsys):
    assert main(["adr", "new", "!!!", "--root", str(tmp_path)]) == 1
    assert "chatur adr new:" in capsys.readouterr().err
