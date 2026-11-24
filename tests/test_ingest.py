"""Ingestion runbook, the jdad-ingest skill, and the P2.1 dry run (roadmap P2.1)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from jdad.kb import KnowledgeBase

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = (REPO_ROOT / "docs" / "ingestion.md").read_text()
SKILL = (REPO_ROOT / "catalog" / "skills" / "jdad-ingest" / "SKILL.md").read_text()
COMMAND = (REPO_ROOT / "commands" / "jdad.md").read_text()
ID_RE = re.compile(r"^- ([a-z0-9.\-]+):", re.MULTILINE)


def _runbook_steps() -> list[str]:
    section = RUNBOOK.split("## Runbook", 1)[1].split("\n## ", 1)[0]
    return re.findall(r"^\d+\. \*\*(.+?)\*\*", section, re.MULTILINE)


def test_runbook_has_every_step_in_order() -> None:
    steps = _runbook_steps()
    assert len(steps) == 10
    for word, step in zip(
        ["Branch", "Watch or read", "Extract", "source record", "Dedupe", "Fold", "Skill", "Version", "Check", "PR"],
        steps,
        strict=True,
    ):
        assert word.lower() in step.lower(), (word, step)


@pytest.mark.parametrize(
    "phrase",
    ["sources/_TEMPLATE.md", "search_practices", "uv run jdad build", "uv run jdad lint-kb", "./verify", "kb_version",
     "There is no transcript step", "Applies when:", "KB addition"],
)
def test_runbook_names_the_commands_and_rules(phrase: str) -> None:
    assert phrase in RUNBOOK


@pytest.mark.parametrize(
    "phrase",
    ["docs/ingestion.md", "sources/_TEMPLATE.md", "Daisy", "write nothing", "search_practices", "uv run jdad build",
     "uv run jdad lint-kb", "./verify", ".claude/projects/", ".remember/", "No transcript step"],
)
def test_skill_checklist_covers_the_runbook(phrase: str) -> None:
    assert phrase in SKILL


def test_skill_guards_against_writing_outside_the_jdad_repo() -> None:
    guard = SKILL.split("## First:", 1)[1].split("\n## ", 1)[0]
    assert "practices/" in guard and "sources/" in guard and "sources/_TEMPLATE.md" in guard
    assert "write nothing" in guard and "Daisy" in guard


def test_jdad_add_still_routes_to_daisy() -> None:
    section = COMMAND.split("## `add`", 1)[1].split("\n## ", 1)[0]
    assert "Daisy" in section
    assert "Do not add the source to the knowledge base yourself" in section


def test_generated_skill_copies_exist() -> None:
    for base in ("skills", "generated/agents-skills"):
        assert (REPO_ROOT / base / "jdad-ingest" / "SKILL.md").is_file()


# ---- the acceptance dry run: one new article through the runbook ----


@pytest.fixture(scope="module")
def kb() -> KnowledgeBase:
    return KnowledgeBase(REPO_ROOT)


def _topic(kb: KnowledgeBase):
    return next(p for p in kb.practices() if p.topic == "agent-tools")


def test_dry_run_source_is_listed(kb: KnowledgeBase) -> None:
    source = next(s for s in kb.list_sources() if s["cite_as"] == "anthropic-tools")
    assert source["items"] == 24 and source["url"].startswith("https://www.anthropic.com/")


def test_dry_run_items_are_one_line_each_not_pasted_text() -> None:
    record = (REPO_ROOT / "sources" / "2026-11-22-anthropic-tools-writing-tools-for-agents.md").read_text()
    items = re.findall(r"^\d+\. (.+)$", record, re.MULTILINE)
    assert len(items) == 24
    assert all(len(item) <= 250 for item in items)


def test_dry_run_rules_all_cite_the_new_source(kb: KnowledgeBase) -> None:
    rules = [rule for section in _topic(kb).sections for rule in section.rules]
    assert len(rules) == 19
    assert all((rule.citation or "").startswith("src: anthropic-tools #") for rule in rules)
    ids = set(ID_RE.findall(kb.get_checklist(["design"])))
    assert {rule.id for rule in rules} <= ids


def test_dry_run_search_finds_a_new_rule(kb: KnowledgeBase) -> None:
    hits = kb.search_practices("actionable tool error messages", tags=["design"], limit=3)
    assert hits[0]["id"] == "tools.respond.actionable-errors"


def test_dry_run_skill_mirrors_the_practice_rules() -> None:
    def rule_lines(path: Path) -> list[str]:
        text = path.read_text()
        if text.startswith("---\n"):
            text = text.split("\n---\n", 1)[1]
        return [line for line in text.splitlines() if line.startswith(("- ", "  ", "## "))]

    assert rule_lines(REPO_ROOT / "catalog/skills/jdad-agent-tools/SKILL.md") == rule_lines(
        REPO_ROOT / "practices/agent-tools.md"
    )
