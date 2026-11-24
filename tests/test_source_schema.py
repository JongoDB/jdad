"""Source file schema and citation resolution (roadmap P1.3, docs/ingestion.md)."""

from __future__ import annotations

from pathlib import Path

import pytest

from jdad.kb import KnowledgeBase, parse_frontmatter
from jdad.lint import lint_kb

REPO_ROOT = Path(__file__).resolve().parents[1]

FIELDS = {
    "title": '"Ten tips"',
    "author": '"@someone"',
    "url": "https://example.com/tips",
    "format": "post",
    "posted": "2026-01-01",
    "retrieved": "2026-01-02",
    "capture": "read the page",
    "items": "10",
    "cite_as": "tips",
}
PRACTICE = "# P\n## A [db]\n- Rule. (src: tips #3) {#p.a.rule}\n"


def source_text(**overrides: str | None) -> str:
    fields = {**FIELDS, **overrides}
    items = fields.get("items") or "0"
    count = int(items) if str(items).isdigit() else 0
    body = ["# Ten tips", f"## The {items} items"] + [f"{n}. Tip {n}." for n in range(1, count + 1)]
    lines = ["---"] + [f"{k}: {v}" for k, v in fields.items() if v is not None] + ["---", *body, ""]
    return "\n".join(lines)


def make_kb(root: Path, sources: dict[str, str], practice: str = PRACTICE) -> Path:
    (root / "practices").mkdir(parents=True)
    (root / "sources").mkdir()
    (root / "practices" / "p.md").write_text(practice)
    for name, text in sources.items():
        (root / "sources" / name).write_text(text)
    return root


def found(root: Path, check: str) -> list[tuple[str, int, str]]:
    return [(f.path, f.line, f.message) for f in lint_kb(root) if f.check == check]


def test_valid_source_and_citation_pass(tmp_path: Path) -> None:
    root = make_kb(tmp_path, {"2026-01-02-tips.md": source_text()})
    assert found(root, "source") == []
    assert found(root, "citation") == []


@pytest.mark.parametrize("field", list(FIELDS))
def test_missing_field_fails(tmp_path: Path, field: str) -> None:
    root = make_kb(tmp_path, {"2026-01-02-tips.md": source_text(**{field: None})})
    messages = [m for _, _, m in found(root, "source")]
    assert any(f"'{field}' is missing or empty" in m for m in messages), messages


@pytest.mark.parametrize(
    ("label", "overrides", "fragment"),
    [
        ("empty value", {"author": '""'}, "'author' is missing or empty"),
        ("unknown field", {"rating": "5"}, "unknown frontmatter field 'rating'"),
        ("bad retrieved date", {"retrieved": "2026-13-01"}, "retrieved '2026-13-01' is not a YYYY-MM-DD date"),
        ("bad posted date", {"posted": "last week"}, "posted 'last week'"),
        ("file date differs", {"retrieved": "2026-01-03"}, "file name date 2026-01-02 differs from retrieved 2026-01-03"),
        ("non-http url", {"url": "ftp://example.com/x"}, "is not an http(s) URL"),
        ("zero items", {"items": "0"}, "items '0' is not a positive integer"),
        ("text items", {"items": "ten"}, "items 'ten' is not a positive integer"),
        ("bad cite_as", {"cite_as": "Tips_2"}, "cite_as 'Tips_2' must be lowercase"),
    ],
)
def test_bad_frontmatter_fails(tmp_path: Path, label: str, overrides: dict, fragment: str) -> None:
    root = make_kb(tmp_path, {"2026-01-02-tips.md": source_text(**overrides)})
    messages = [m for _, _, m in found(root, "source")]
    assert any(fragment in m for m in messages), f"{label}: {messages}"


def test_posted_may_be_unknown(tmp_path: Path) -> None:
    root = make_kb(tmp_path, {"2026-01-02-tips.md": source_text(posted="unknown")})
    assert found(root, "source") == []


def test_no_frontmatter_fails(tmp_path: Path) -> None:
    root = make_kb(tmp_path, {"2026-01-02-tips.md": "# Ten tips\n- Link: https://example.com\n"})
    assert ("sources/2026-01-02-tips.md", 1, "no frontmatter: the file must start with a '---' line") in found(root, "source")


def test_unclosed_and_nested_frontmatter_fail(tmp_path: Path) -> None:
    root = make_kb(tmp_path, {"2026-01-02-tips.md": "---\ntitle: x\n  nested: y\n"})
    messages = [m for _, _, m in found(root, "source")]
    assert any("never closed" in m for m in messages)
    assert any("not a 'key: value' line" in m for m in messages)


def test_duplicate_cite_as_fails(tmp_path: Path) -> None:
    root = make_kb(
        tmp_path,
        {"2026-01-02-tips.md": source_text(), "2026-01-02-tips-again.md": source_text(title='"Again"')},
    )
    messages = [m for _, _, m in found(root, "source")]
    assert any("cite_as 'tips' is already used by sources/2026-01-02-tips-again.md" in m for m in messages), messages


# ---- citation resolution ---------------------------------------------------


@pytest.mark.parametrize(
    ("citation", "fragment"),
    [
        ("(src: nosuch #1)", "no source has cite_as 'nosuch'"),
        ("(src: tips #11)", "item(s) #11 outside 1..10"),
        ("(src: tips #0, #4)", "item(s) #0 outside 1..10"),
        ("(src: tips)", "isn't '(src: <cite_as> #n[, #m])'"),
        ("(src: Tips #1)", "isn't '(src: <cite_as> #n[, #m])'"),
    ],
)
def test_bad_citation_fails(tmp_path: Path, citation: str, fragment: str) -> None:
    practice = f"# P\n## A [db]\n- Rule. {citation} {{#p.a.rule}}\n"
    root = make_kb(tmp_path, {"2026-01-02-tips.md": source_text()}, practice)
    messages = [(path, line, m) for path, line, m in found(root, "citation")]
    assert any(path == "practices/p.md" and line == 3 and fragment in m for path, line, m in messages), messages


def test_kb_addition_needs_no_source(tmp_path: Path) -> None:
    root = make_kb(tmp_path, {}, "# P\n## A [db]\n- Measure first. (KB addition) {#p.a.zero}\n")
    assert found(root, "citation") == []


# ---- the repo and the tools ------------------------------------------------


def test_repo_sources_follow_the_schema() -> None:
    assert [f for f in lint_kb(REPO_ROOT) if f.check in {"source", "citation"}] == []


def test_list_sources_returns_the_new_fields() -> None:
    sources = KnowledgeBase(REPO_ROOT).list_sources()
    assert "2026-11-22-breakingbreach-app-performance" in [s["id"] for s in sources]
    entry = next(s for s in sources if s["id"] == "2026-11-22-breakingbreach-app-performance")
    assert entry["cite_as"] == "breakingbreach"
    assert entry["items"] == 31
    assert entry["format"] == "reel"
    assert entry["posted"] == "2026-11-01"
    assert entry["retrieved"] == "2026-11-22"
    assert entry["url"] == entry["link"] == "https://www.instagram.com/reel/DfMYnLZyQOE/"
    assert entry["title"].startswith("@breakingbreach")
    assert entry["author"] and entry["capture"]


def test_template_is_not_a_source(newest_entry: str) -> None:
    kb = KnowledgeBase(REPO_ROOT)
    assert (REPO_ROOT / "sources" / "_TEMPLATE.md").is_file()
    assert all(not s["id"].startswith("_") for s in kb.list_sources())
    assert kb.version()["newest_entry"] == newest_entry
    fields, problems = parse_frontmatter((REPO_ROOT / "sources" / "_TEMPLATE.md").read_text())
    assert problems == []
    assert set(fields) == {"title", "author", "url", "format", "posted", "retrieved", "capture", "items", "cite_as"}


# Checker batch 3 (#17 gaps): item counts and _-prefixed files.


def _source_findings(tmp_path: Path, text: str) -> list[str]:
    root = make_kb(tmp_path, {"2026-01-02-tips.md": text})
    return [f.message for f in lint_kb(root) if f.check == "source"]


def test_items_heading_must_match_the_count(tmp_path: Path) -> None:
    text = source_text().replace("## The 10 items", "## The 9 items")
    assert any("heading says 9" in m for m in _source_findings(tmp_path, text))


def test_items_heading_is_required(tmp_path: Path) -> None:
    text = source_text().replace("## The 10 items", "## Tips")
    assert any("'## The N items'" in m for m in _source_findings(tmp_path, text))


def test_numbered_items_must_run_one_to_items(tmp_path: Path) -> None:
    gap = source_text().replace("\n7. Tip 7.", "")
    assert any("numbered items" in m for m in _source_findings(tmp_path / "gap", gap))
    extra = source_text().replace("10. Tip 10.", "10. Tip 10.\n11. Tip 11.")
    assert any("numbered items" in m for m in _source_findings(tmp_path / "extra", extra))


def test_inline_item_lists_need_only_the_heading(tmp_path: Path) -> None:
    head = source_text().split("## The 10 items")[0]
    text = head + "## The 10 items, verbatim\n1 One. 2 Two. 3 Three. 4 Four. 5 Five. 6 Six. 7 Seven. 8 Eight. 9 Nine. 10 Ten.\n"
    assert _source_findings(tmp_path, text) == []


@pytest.mark.parametrize("name", ["_TEMPLATE", "_TEMPLATE.md", "TEMPLATE", "template"])
def test_underscore_files_are_never_served(name: str) -> None:
    with pytest.raises(FileNotFoundError):
        KnowledgeBase(REPO_ROOT).get_source(name)


def test_underscore_practice_files_are_never_served(tmp_path: Path) -> None:
    root = make_kb(tmp_path, {})
    (root / "practices" / "_draft.md").write_text("# Draft\n")
    with pytest.raises(FileNotFoundError):
        KnowledgeBase(root).get_practice("_draft")


# Checker 12B (JON-1360): duplicate keys, title preference, _-prefixed files.


def test_duplicate_frontmatter_key_fails(tmp_path: Path) -> None:
    text = source_text().replace("format: post\n", "format: post\nformat: reel\n")
    assert any("duplicate key 'format'" in m for m in _source_findings(tmp_path, text))


def test_list_sources_prefers_the_frontmatter_title(tmp_path: Path) -> None:
    text = source_text(title='"Frontmatter title"')
    assert "# Ten tips" in text
    root = make_kb(tmp_path, {"2026-01-02-tips.md": text})
    assert [s["title"] for s in KnowledgeBase(root).list_sources()] == ["Frontmatter title"]


def test_list_sources_falls_back_to_the_heading(tmp_path: Path) -> None:
    root = make_kb(tmp_path, {"2026-01-02-tips.md": source_text(title=None)})
    assert [s["title"] for s in KnowledgeBase(root).list_sources()] == ["Ten tips"]


def test_underscore_files_are_left_out_of_listings(tmp_path: Path) -> None:
    root = make_kb(tmp_path, {"2026-01-02-tips.md": source_text(), "_2099-01-01-draft.md": source_text()})
    (root / "practices" / "_2099-01-01-draft.md").write_text("# Draft\n## D [db]\n- Draft rule. (KB addition) {#d.d.rule}\n")
    kb = KnowledgeBase(root)
    assert [s["id"] for s in kb.list_sources()] == ["2026-01-02-tips"]
    assert [t["topic"] for t in kb.list_topics()] == ["p"]
    assert kb.newest_entry_date() == "2026-01-02"
