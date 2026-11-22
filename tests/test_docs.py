"""Structure checks for the agent-facing docs: roadmap items, relative links, file sizes."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ROADMAP = REPO_ROOT / "ROADMAP.md"
DOC_FILES = [
    REPO_ROOT / "AGENTS.md",
    REPO_ROOT / "CLAUDE.md",
    ROADMAP,
    *sorted((REPO_ROOT / "docs").rglob("*.md")),
]

ITEM_RE = re.compile(r"^- \[( |x)\] \*\*(P(\d+)\.(\d+)) ", re.MULTILINE)
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def _items() -> list[tuple[str, int, int, str]]:
    """Return (id, phase, number, body) for every roadmap item."""
    text = ROADMAP.read_text()
    matches = list(ITEM_RE.finditer(text))
    items = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[match.start() : end]
        body = body.split("\n## ", 1)[0]
        items.append((match.group(2), int(match.group(3)), int(match.group(4)), body))
    return items


def test_roadmap_ids_are_unique_and_ordered() -> None:
    items = _items()
    assert len(items) >= 30
    ids = [item_id for item_id, *_ in items]
    assert len(ids) == len(set(ids)), "duplicate roadmap IDs"
    keys = [(phase, number) for _, phase, number, _ in items]
    assert keys == sorted(keys), "roadmap items must stay in phase and number order"


@pytest.mark.parametrize("field", ["Goal", "Deliverables", "Acceptance", "Depends on"])
def test_items_have_required_fields(field: str) -> None:
    missing = []
    for item_id, phase, _, body in _items():
        if phase == 0:
            continue
        if field == "Goal" and phase > 1:
            continue  # later phases state the goal once, under the phase heading
        if f"{field}:" not in body:
            missing.append(item_id)
    assert not missing, f"items missing '{field}:': {missing}"


def test_needs_jon_items_are_marked_in_bold() -> None:
    text = ROADMAP.read_text()
    assert "Needs Jon" in text
    assert "Needs Jon:**" not in text.replace("**Needs Jon:**", "")


@pytest.mark.parametrize("path", DOC_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_relative_links_resolve(path: Path) -> None:
    broken = []
    for target in LINK_RE.findall(path.read_text()):
        if re.match(r"^[a-z]+:", target) or target.startswith("#"):
            continue
        file_part = target.split("#", 1)[0]
        if not (path.parent / file_part).exists():
            broken.append(target)
    assert not broken, f"broken relative links in {path.name}: {broken}"


def test_instruction_files_stay_short() -> None:
    agents = (REPO_ROOT / "AGENTS.md").read_text()
    assert len(agents.splitlines()) <= 150
    assert len(agents.encode()) < 32 * 1024  # Codex project_doc_max_bytes default
    assert "@AGENTS.md" in (REPO_ROOT / "CLAUDE.md").read_text()
