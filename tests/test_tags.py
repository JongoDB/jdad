"""Tag taxonomy v2 (roadmap P2.3): six new tags, each seeded in a fixture KB."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from jdad.kb import KNOWN_TAGS, KnowledgeBase
from jdad.lint import lint_kb

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "tags"
NEW_TAGS = ("security", "supply-chain", "ci", "process", "design", "ux")
SEEDED = {
    "security": "tags.security.no-secrets",
    "supply-chain": "tags.supply-chain.lockfile",
    "ci": "tags.ci.required-check",
    "process": "tags.process.plan-first",
    "design": "tags.design.version-apis",
    "ux": "tags.ux.actionable-errors",
}
CONTROL = "tags.backend.paginate"
ALL_IDS = {*SEEDED.values(), CONTROL}
ID_RE = re.compile(r"^- \[ \] ([a-z0-9.\-]+):", re.MULTILINE)  # checklist lines (P3.3)


def test_all_six_tags_are_known() -> None:
    assert set(NEW_TAGS) <= set(KNOWN_TAGS)
    assert len(KNOWN_TAGS) == len(set(KNOWN_TAGS)) == 12


def test_fixture_lints_clean() -> None:
    assert lint_kb(FIXTURE) == []


@pytest.mark.parametrize("tag", NEW_TAGS)
def test_checklist_returns_only_the_seeded_rule(tag: str) -> None:
    ids = set(ID_RE.findall(KnowledgeBase(FIXTURE).get_checklist([tag])))
    assert ids == {SEEDED[tag]}
    assert not ids & (ALL_IDS - {SEEDED[tag]})


@pytest.mark.parametrize("tag", NEW_TAGS)
def test_lint_accepts_the_tag(tag: str, tmp_path: Path) -> None:
    (tmp_path / "practices").mkdir()
    (tmp_path / "sources").mkdir()
    (tmp_path / "practices" / "t.md").write_text(
        f"# T\n## Section [{tag}]\n- Do the thing. (KB addition) {{#t.{tag}.thing}}\n"
    )
    assert lint_kb(tmp_path) == []


@pytest.mark.parametrize("bad", ["securty", "supplychain", "cicd", "Process", "ui"])
def test_unknown_tag_fails_lint_naming_the_tag(bad: str, tmp_path: Path) -> None:
    shutil.copytree(FIXTURE, tmp_path / "kb")
    practice = tmp_path / "kb" / "practices" / "tags.md"
    practice.write_text(practice.read_text().replace("## Experience [ux]", f"## Experience [{bad}]"))
    findings = [f for f in lint_kb(tmp_path / "kb") if f.check == "tag"]
    assert findings, f"[{bad}] passed lint"
    assert any(f"[{bad.lower()}]" in f.message or f"[{bad}]" in f.message for f in findings)


@pytest.mark.parametrize(
    "path",
    ["README.md", "commands/jdad.md", "docs/kb-schema.md", "AGENTS.md", "src/jdad/server.py"],
)
def test_every_place_that_lists_tags_lists_all_twelve(path: str) -> None:
    text = (REPO_ROOT / path).read_text()
    missing = [tag for tag in KNOWN_TAGS if tag not in text]
    assert not missing, f"{path} doesn't mention {missing}"


@pytest.mark.parametrize("place", ["search_practices", "get_checklist", "review_against_kb", "apply-kb"])
def test_each_tool_text_that_lists_tags_lists_all_twelve(place: str) -> None:
    """Checker 12B (JON-1360): each docstring or prompt that lists the tags
    lists every one, not just server.py as a whole."""
    from jdad import server

    text = server.apply_kb() if place == "apply-kb" else getattr(server, place).__doc__
    missing = [tag for tag in KNOWN_TAGS if tag not in text]
    assert not missing, f"{place} doesn't list {missing}"
