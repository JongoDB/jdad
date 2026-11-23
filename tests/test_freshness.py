"""Citation integrity and source freshness (roadmap P2.5), with the date frozen."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from jdad.cli import main
from jdad.freshness import freshness_report

REPO_ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2027, 6, 1)


def source(cite_as: str, posted: str, retrieved: str = "2026-01-02", items: int = 3) -> str:
    body = "\n".join(f"{n}. Tip {n}." for n in range(1, items + 1))
    return (
        f'---\ntitle: "{cite_as}"\nauthor: "@x"\nurl: https://example.com/{cite_as}\nformat: post\n'
        f"posted: {posted}\nretrieved: {retrieved}\ncapture: read the page\nitems: {items}\ncite_as: {cite_as}\n---\n"
        f"# {cite_as}\n## The {items} items\n{body}\n"
    )


def make_kb(root: Path, sources: dict[str, str], practices: dict[str, str]) -> Path:
    (root / "practices").mkdir(parents=True)
    (root / "sources").mkdir()
    for name, text in practices.items():
        (root / "practices" / name).write_text(text)
    for name, text in sources.items():
        (root / "sources" / name).write_text(text)
    return root


def practice(prefix: str, *cites: str) -> str:
    rules = "\n".join(f"- Rule {i}. (src: {c} #1) {{#{prefix}.a.r{i}}}" for i, c in enumerate(cites))
    return f"# {prefix}\n## A [backend]\n{rules}\n"


# ---- the freshness report ----


def test_old_source_with_a_newer_same_topic_peer_is_reported(tmp_path: Path) -> None:
    root = make_kb(
        tmp_path,
        {"2026-01-02-old.md": source("old", "2025-01-10"), "2026-01-02-new.md": source("new", "2026-09-01")},
        {"api.md": practice("api", "old", "new")},
    )
    assert freshness_report(root, TODAY) == ["2026-01-02-old (2025-01-10) -> 2026-01-02-new (2026-09-01) [topic api]"]


def test_old_source_without_a_newer_peer_is_not_reported(tmp_path: Path) -> None:
    root = make_kb(
        tmp_path,
        {"2026-01-02-old.md": source("old", "2025-01-10"), "2026-01-02-other.md": source("other", "2026-09-01")},
        {"api.md": practice("api", "old"), "ui.md": practice("ui", "other")},  # newer source, different topic
    )
    assert freshness_report(root, TODAY) == []


def test_sources_a_year_old_or_less_are_not_reported(tmp_path: Path) -> None:
    root = make_kb(
        tmp_path,
        {"2026-01-02-a.md": source("a", "2026-06-01"), "2026-01-02-b.md": source("b", "2027-01-01")},
        {"api.md": practice("api", "a", "b")},
    )
    assert freshness_report(root, TODAY) == []  # exactly 365 days old
    assert freshness_report(root, date(2027, 6, 2)) == [
        "2026-01-02-a (2026-06-01) -> 2026-01-02-b (2027-01-01) [topic api]"
    ]


def test_unknown_posted_date_falls_back_to_retrieved(tmp_path: Path) -> None:
    root = make_kb(
        tmp_path,
        {"2025-02-01-old.md": source("old", "unknown", "2025-02-01"), "2026-01-02-new.md": source("new", "2026-03-01")},
        {"api.md": practice("api", "old", "new")},
    )
    assert freshness_report(root, TODAY) == ["2025-02-01-old (2025-02-01) -> 2026-01-02-new (2026-03-01) [topic api]"]


def test_uncited_sources_and_multiple_topics(tmp_path: Path) -> None:
    root = make_kb(
        tmp_path,
        {
            "2026-01-02-old.md": source("old", "2024-01-01"),
            "2026-01-02-mid.md": source("mid", "2025-01-01"),
            "2026-01-02-new.md": source("new", "2026-01-01"),
            "2026-01-02-lonely.md": source("lonely", "2020-01-01"),  # cited by nothing: no topic, never reported
        },
        {"api.md": practice("api", "old", "new", "mid"), "ui.md": practice("ui", "old", "mid")},
    )
    assert freshness_report(root, TODAY) == [
        "2026-01-02-old (2024-01-01) -> 2026-01-02-mid (2025-01-01) [topic api]",
        "2026-01-02-old (2024-01-01) -> 2026-01-02-new (2026-01-01) [topic api]",
        "2026-01-02-mid (2025-01-01) -> 2026-01-02-new (2026-01-01) [topic api]",
        "2026-01-02-old (2024-01-01) -> 2026-01-02-mid (2025-01-01) [topic ui]",
    ]


def test_repo_has_nothing_stale_today() -> None:
    assert freshness_report(REPO_ROOT, date(2026, 11, 22)) == []


def test_cli_reports_and_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_kb(
        tmp_path,
        {"2026-01-02-old.md": source("old", "2025-01-10"), "2026-01-02-new.md": source("new", "2026-09-01")},
        {"api.md": practice("api", "old", "new")},
    )
    assert main(["freshness", "--root", str(root), "--today", "2027-06-01"]) == 0
    assert "2026-01-02-old (2025-01-10) -> 2026-01-02-new (2026-09-01) [topic api]" in capsys.readouterr().out
    assert main(["freshness", "--root", str(root), "--today", "2027-06-01", "--strict"]) == 1
    assert main(["freshness", "--root", str(root), "--today", "2025-06-01", "--strict"]) == 0
    assert "no stale sources" in capsys.readouterr().out


# ---- citation integrity, through the lint CLI ----


@pytest.mark.parametrize(
    ("citation", "named"),
    [("(src: nosuch #1)", "(src: nosuch #1)"), ("(src: tips #9)", "(src: tips #9)"), ("(src: tips #2, #7)", "(src: tips #2, #7)")],
)
def test_lint_fails_and_names_a_broken_citation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], citation: str, named: str
) -> None:
    root = make_kb(
        tmp_path,
        {"2026-01-02-tips.md": source("tips", "2026-01-01")},
        {"p.md": f"# P\n## A [db]\n- Rule. {citation} {{#p.a.rule}}\n"},
    )
    assert main(["lint-kb", "--root", str(root)]) == 1
    out = capsys.readouterr().out
    assert named in out, out
