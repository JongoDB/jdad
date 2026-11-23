"""Agentic-workflow topic from the harness research (roadmap P2.4)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from jdad.kb import KnowledgeBase

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCES = {"openai-harness", "anthropic-harnesses", "anthropic-harness-design", "cc-best-practices"}
ID_RE = re.compile(r"^- ([a-z0-9.\-]+):", re.MULTILINE)


@pytest.fixture(scope="module")
def kb() -> KnowledgeBase:
    return KnowledgeBase(REPO_ROOT)


def _workflow(kb: KnowledgeBase):
    return next(p for p in kb.practices() if p.topic == "agentic-workflow")


def _rules(kb: KnowledgeBase):
    return [rule for section in _workflow(kb).sections for rule in section.rules]


def test_topic_and_sources_are_listed(kb: KnowledgeBase) -> None:
    assert "agentic-workflow" in {t["topic"] if isinstance(t, dict) else t for t in kb.list_topics()}
    listed = {s["cite_as"] for s in kb.list_sources()}
    assert SOURCES <= listed


def test_every_section_is_process(kb: KnowledgeBase) -> None:
    assert all("process" in section.tags for section in _workflow(kb).sections)


def test_every_rule_cites_a_harness_source_or_is_a_kb_addition(kb: KnowledgeBase) -> None:
    rules = _rules(kb)
    assert len(rules) >= 40
    for rule in rules:
        if rule.origin == "kb-addition":
            continue
        source = re.match(r"src: ([a-z0-9-]+) #", rule.citation or "")
        assert source and source.group(1) in SOURCES, rule.id


def test_process_checklist_returns_every_workflow_rule(kb: KnowledgeBase) -> None:
    ids = set(ID_RE.findall(kb.get_checklist(["process"])))
    assert {rule.id for rule in _rules(kb)} <= ids


def test_search_finds_workflow_rules(kb: KnowledgeBase) -> None:
    hits = kb.search_practices("evidence of verification", tags=["process"], limit=3)
    assert hits[0]["id"] == "wf.verify.evidence"


def test_workflow_skill_mirrors_the_practice_rules() -> None:
    """The skill's rules are a hand-written copy of the practice file's (in
    catalog/, compiled into skills/ by `jdad build`), so they must match.
    Frontmatter is skipped: its indented lines (`  generated: ...`) aren't rules."""

    def rule_lines(path: Path) -> list[str]:
        lines = path.read_text().splitlines()
        if lines and lines[0] == "---":
            lines = lines[lines.index("---", 1) + 1 :]
        return [line for line in lines if line.startswith(("- ", "  ", "## "))]

    assert rule_lines(REPO_ROOT / "skills/jdad-workflow/SKILL.md") == rule_lines(
        REPO_ROOT / "practices/agentic-workflow.md"
    )
