"""Canonical skills catalog (roadmap P1.4): one failing fixture per spec rule."""

from __future__ import annotations

from pathlib import Path

import pytest

from jdad.catalog import main, parse_frontmatter, validate_catalog

REPO_ROOT = Path(__file__).resolve().parents[1]
GOOD_SKILL = "---\nname: {name}\ndescription: Use when testing the catalog.\n---\n# Body\n"


def make_skill(root: Path, directory: str, text: str) -> Path:
    path = root / "catalog" / "skills" / directory / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return root


def messages(root: Path) -> list[str]:
    return [f.message for f in validate_catalog(root)]


def test_good_skill_passes(tmp_path: Path) -> None:
    root = make_skill(tmp_path, "good-skill", GOOD_SKILL.format(name="good-skill"))
    assert messages(root) == []


@pytest.mark.parametrize(
    ("label", "directory", "text", "fragment"),
    [
        ("name differs from directory", "good-skill", GOOD_SKILL.format(name="other-skill"), "must equal its directory name"),
        ("uppercase name", "Bad-Skill", GOOD_SKILL.format(name="Bad-Skill"), "lowercase letters, digits and single hyphens"),
        ("double hyphen", "bad--skill", GOOD_SKILL.format(name="bad--skill"), "lowercase letters, digits and single hyphens"),
        ("leading hyphen", "-bad", GOOD_SKILL.format(name="-bad"), "lowercase letters, digits and single hyphens"),
        ("underscore", "bad_skill", GOOD_SKILL.format(name="bad_skill"), "lowercase letters, digits and single hyphens"),
        ("name over 64", "a" * 65, GOOD_SKILL.format(name="a" * 65), "65 characters (at most 64)"),
        (
            "description over 1024",
            "long-desc",
            "---\nname: long-desc\ndescription: " + "x" * 1025 + "\n---\n",
            "1025 characters (at most 1024)",
        ),
        ("body of 500 lines", "long-body", GOOD_SKILL.format(name="long-body") + "line\n" * 499, "keep it under 500"),
        (
            "unknown top-level key",
            "extra-key",
            "---\nname: extra-key\ndescription: d\ndisable-model-invocation: true\n---\n",
            "unknown frontmatter key 'disable-model-invocation'",
        ),
        ("missing name", "no-name", "---\ndescription: d\n---\n", "'name' is required"),
        ("missing description", "no-desc", "---\nname: no-desc\n---\n", "'description' is required"),
        ("no frontmatter", "no-front", "# just a body\n", "no frontmatter"),
        ("metadata not a mapping", "meta-str", "---\nname: meta-str\ndescription: d\nmetadata: oops\n---\n", "'metadata' must be a mapping"),
        (
            "compatibility over 500",
            "compat",
            "---\nname: compat\ndescription: d\ncompatibility: " + "c" * 501 + "\n---\n",
            "'compatibility' must be text of at most 500",
        ),
    ],
)
def test_spec_rule_fails(tmp_path: Path, label: str, directory: str, text: str, fragment: str) -> None:
    found = messages(make_skill(tmp_path, directory, text))
    assert any(fragment in m for m in found), f"{label}: {found}"


def test_body_of_499_lines_passes(tmp_path: Path) -> None:
    root = make_skill(tmp_path, "edge", "---\nname: edge\ndescription: d\n---\n" + "line\n" * 499)
    assert messages(root) == []


def test_tool_extras_go_under_metadata(tmp_path: Path) -> None:
    text = "---\nname: extras\ndescription: d\nmetadata:\n  claude:\n    disable-model-invocation: true\n---\n"
    assert messages(make_skill(tmp_path, "extras", text)) == []
    meta = parse_frontmatter("name: x\nmetadata:\n  claude:\n    disable-model-invocation: true\n  tags: [a, b]\n")
    assert meta["metadata"] == {"claude": {"disable-model-invocation": True}, "tags": ["a", "b"]}


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("---\nglobs: '**/*.py'\n---\n", "'description' is required"),
        ("---\ndescription: d\nalwaysApply: yes-please\n---\n", "'alwaysApply' must be true or false"),
        ("---\ndescription: d\nscope: all\n---\n", "unknown frontmatter key 'scope'"),
    ],
)
def test_rule_files_are_checked(tmp_path: Path, text: str, fragment: str) -> None:
    path = tmp_path / "catalog" / "rules" / "r.md"
    path.parent.mkdir(parents=True)
    path.write_text(text)
    assert any(fragment in m for m in messages(tmp_path))


def test_good_rule_passes(tmp_path: Path) -> None:
    path = tmp_path / "catalog" / "rules" / "py.md"
    path.parent.mkdir(parents=True)
    path.write_text("---\ndescription: Python files\nglobs:\n  - '**/*.py'\nalwaysApply: false\n---\nUse ruff.\n")
    assert messages(tmp_path) == []


def test_repo_catalog_is_valid_and_has_the_performance_skill() -> None:
    assert validate_catalog(REPO_ROOT) == []
    assert (REPO_ROOT / "catalog" / "skills" / "jdad-performance" / "SKILL.md").is_file()


def test_plugin_skills_come_from_the_catalog() -> None:
    """skills/ is `jdad build` output since P1.5 (tests/test_build.py checks it's current)."""
    catalog = REPO_ROOT / "catalog" / "skills"
    plugin = REPO_ROOT / "skills"
    assert sorted(p.name for p in catalog.iterdir() if p.is_dir()) == sorted(p.name for p in plugin.iterdir() if p.is_dir())


def test_cli_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", str(REPO_ROOT)]) == 0
    make_skill(tmp_path, "bad_name", GOOD_SKILL.format(name="bad_name"))
    assert main(["validate", str(tmp_path)]) == 1
    assert "bad_name" in capsys.readouterr().out
    assert main([]) == 2
