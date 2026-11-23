"""AGENTS.md is the canonical instructions file (roadmap P1.1, ADR 0004).

Every normative rule has an ID R-<area>-<n>, listed in AGENTS.md's Rules
table. Each ID is defined exactly once: as a table row in AGENTS.md, or as a
bullet in CLAUDE.md's "Claude-only" section (its AGENTS.md row then just
points there). Nothing is restated in both files, because Grok Build loads
both.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENTS = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
CLAUDE = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")

ID_RE = re.compile(r"\bR-[a-z]+-\d+\b")
ROW_RE = re.compile(r"^\| (R-[a-z]+-\d+) \| (.+) \|$", re.MULTILINE)
CLAUDE_ONLY_ROW = "Claude-only: CLAUDE.md"
BULLET_RE = re.compile(r"^- \*\*(R-[a-z]+-\d+)\*\* (.+)$", re.MULTILINE)


def _rows() -> list[tuple[str, str]]:
    return ROW_RE.findall(AGENTS)


def _claude_only_section() -> str:
    match = re.search(r"^## Claude-only\n(.*?)(?=^## |\Z)", CLAUDE, re.MULTILINE | re.DOTALL)
    assert match, "CLAUDE.md has no '## Claude-only' section"
    return match.group(1)


def test_sizes() -> None:
    assert len(AGENTS.splitlines()) <= 120
    assert len(AGENTS.encode()) < 32 * 1024  # Codex project_doc_max_bytes default
    assert len(CLAUDE.splitlines()) <= 40
    assert "@AGENTS.md" in CLAUDE


def test_rule_ids_are_unique_and_numbered_per_area() -> None:
    ids = [rule_id for rule_id, _ in _rows()]
    assert ids, "AGENTS.md has no Rules table rows"
    assert len(ids) == len(set(ids)), f"duplicate rule IDs: {sorted(i for i in ids if ids.count(i) > 1)}"
    by_area: dict[str, list[int]] = {}
    for rule_id in ids:
        _, area, number = rule_id.split("-")
        by_area.setdefault(area, []).append(int(number))
    for area, numbers in by_area.items():
        assert sorted(numbers) == list(range(1, len(numbers) + 1)), f"R-{area}-* has gaps: {sorted(numbers)}"


def test_every_id_is_defined_exactly_once() -> None:
    in_agents = {rule_id for rule_id, text in _rows() if not text.startswith(CLAUDE_ONLY_ROW)}
    pointers = {rule_id for rule_id, text in _rows() if text.startswith(CLAUDE_ONLY_ROW)}
    in_claude = [rule_id for rule_id, _ in BULLET_RE.findall(_claude_only_section())]
    assert len(in_claude) == len(set(in_claude)), "an ID is defined twice in CLAUDE.md"
    assert set(in_claude) == pointers, (
        f"Claude-only IDs and AGENTS.md pointer rows differ: "
        f"only in CLAUDE.md {set(in_claude) - pointers}, only pointed to {pointers - set(in_claude)}"
    )
    assert not in_agents & set(in_claude), f"defined in both files: {in_agents & set(in_claude)}"


def test_no_rule_ids_outside_their_homes() -> None:
    claude_outside = CLAUDE.replace(_claude_only_section(), "")
    assert not ID_RE.findall(claude_outside), "rule IDs in CLAUDE.md outside its Claude-only section"
    table_ids = {rule_id for rule_id, _ in _rows()}
    mentioned = set(ID_RE.findall(AGENTS))
    assert mentioned <= table_ids, f"AGENTS.md mentions IDs with no table row: {mentioned - table_ids}"


def test_claude_md_restates_nothing_from_agents_md() -> None:
    agents_lines = {line.strip() for line in AGENTS.splitlines() if len(line.strip()) >= 40}
    repeated = [line.strip() for line in CLAUDE.splitlines() if line.strip() in agents_lines]
    assert not repeated, f"lines in both files: {repeated}"
    # The distinctive rules that used to live in CLAUDE.md now live only in AGENTS.md.
    for phrase in ("lockstep", "kb://practices/", "--no-optional-locks", "Deduplicate", "_TEMPLATE.md"):
        assert phrase in AGENTS, phrase
        assert phrase not in CLAUDE, phrase
