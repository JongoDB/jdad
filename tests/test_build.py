"""Skill compiler v0, `jdad build` (roadmap P1.5): golden files per target,
stale detection, and the repo's own outputs."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from jdad.build import BuildError, build, check, dump_frontmatter
from jdad.cli import main

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "compiler"  # not "build": .gitignore ignores build/
OUTPUT_DIRS = ("skills", "generated")


def files(root: Path) -> dict[str, bytes]:
    out = {}
    for name in OUTPUT_DIRS:
        base = root / name
        if base.is_dir():
            out |= {p.relative_to(root).as_posix(): p.read_bytes() for p in base.rglob("*") if p.is_file()}
    return out


@pytest.fixture
def work(tmp_path: Path) -> Path:
    shutil.copytree(FIXTURE / "catalog", tmp_path / "catalog")
    return tmp_path


def test_golden_files_for_every_target(work: Path) -> None:
    build(work)
    expected = files(FIXTURE)
    assert set(expected) == {
        "skills/demo-skill/SKILL.md",
        "skills/demo-skill/references/notes.md",
        "generated/agents-skills/demo-skill/SKILL.md",
        "generated/agents-skills/demo-skill/references/notes.md",
        "generated/cursor-rules/python.mdc",
    }
    assert files(work) == expected


def test_targets_handle_tool_extras(work: Path) -> None:
    build(work)
    claude = (work / "skills/demo-skill/SKILL.md").read_text()
    agents = (work / "generated/agents-skills/demo-skill/SKILL.md").read_text()
    assert "\ndisable-model-invocation: true\n" in claude  # lifted to Claude's frontmatter
    assert "disable-model-invocation" not in agents  # spec-only for .agents/skills
    for text in (claude, agents):
        assert "cursor:" not in text and "ignored" not in text
        assert "  generated: jdad build from catalog/skills/demo-skill/SKILL.md; do not edit\n" in text
    mdc = (work / "generated/cursor-rules/python.mdc").read_text()
    assert mdc.startswith('---\ndescription: Python files in this repo\nglobs: "**/*.py,scripts/*.py"\nalwaysApply: false\n---\n')


def test_check_is_clean_after_build_and_writes_nothing(work: Path) -> None:
    assert check(work)  # nothing built yet
    assert files(work) == {}
    build(work)
    assert check(work) == []
    assert build(work) == []  # idempotent


def test_editing_a_catalog_skill_without_rebuilding_fails(work: Path) -> None:
    build(work)
    skill = work / "catalog/skills/demo-skill/SKILL.md"
    skill.write_text(skill.read_text().replace("# Demo", "# Demo, edited"))
    assert check(work) == ["stale: skills/demo-skill/SKILL.md", "stale: generated/agents-skills/demo-skill/SKILL.md"]
    assert main(["build", "--check", "--root", str(work)]) == 1


def test_hand_edited_or_extra_outputs_fail_and_build_repairs_them(work: Path) -> None:
    build(work)
    (work / "skills/demo-skill/SKILL.md").write_text("hand edit\n")
    (work / "skills/orphan").mkdir()
    (work / "skills/orphan/SKILL.md").write_text("---\nname: orphan\n---\n")
    assert set(check(work)) == {"stale: skills/demo-skill/SKILL.md", "not generated from the catalog: skills/orphan/SKILL.md"}
    build(work)
    assert check(work) == []
    assert not (work / "skills/orphan").exists()


def test_invalid_catalog_refuses_to_build(work: Path) -> None:
    skill = work / "catalog/skills/demo-skill/SKILL.md"
    skill.write_text(skill.read_text().replace("name: demo-skill", "name: Demo_Skill"))
    with pytest.raises(BuildError, match="catalog is invalid"):
        build(work)
    assert main(["build", "--root", str(work)]) == 1


def test_claude_extra_colliding_with_a_top_level_key_fails(work: Path) -> None:
    skill = work / "catalog/skills/demo-skill/SKILL.md"
    skill.write_text(skill.read_text().replace("    disable-model-invocation: true", "    license: GPL"))
    with pytest.raises(BuildError, match="collides"):
        build(work)


def test_emitter_quotes_only_when_needed() -> None:
    text = dump_frontmatter({"a": "plain text, with commas", "b": "has: colon", "c": "*glob", "d": True, "e": ["x", "y z"]})
    assert text == 'a: plain text, with commas\nb: "has: colon"\nc: "*glob"\nd: true\ne:\n  - x\n  - y z'


def test_repo_outputs_are_current() -> None:
    assert check(REPO_ROOT) == []


def test_generated_claude_skill_is_the_catalog_skill_plus_the_header() -> None:
    """Acceptance: the generated skill equals the hand-written one (now the
    catalog source) apart from the generated-file header."""
    source = (REPO_ROOT / "catalog/skills/jdad-performance/SKILL.md").read_text()
    generated = (REPO_ROOT / "skills/jdad-performance/SKILL.md").read_text()
    header = "metadata:\n  generated: jdad build from catalog/skills/jdad-performance/SKILL.md; do not edit\n"
    assert header in generated
    assert generated.replace(header, "", 1) == source
