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


def test_needs_jon_markers_are_bold_and_say_what_is_needed() -> None:
    items = _items()
    marked = [item_id for item_id, *_, body in items if "Needs Jon" in body]
    assert marked, "expected at least one Needs Jon item"
    bad = []
    for item_id, *_, body in items:
        total = body.count("Needs Jon")
        good = len(re.findall(r"\*\*Needs Jon:\*\* \S", body))
        if total != good:
            bad.append(item_id)
    assert not bad, f"'Needs Jon' must be written '**Needs Jon:** <what>' in: {bad}"


ESCAPE_HATCH_RE = re.compile(
    r"or (?:is )?listed as unverified|otherwise lists? it as unverified|otherwise the PR says"
    r"|or the gap is listed|otherwise unverified",
    re.IGNORECASE,
)


# "unverified" is only allowed as the reason an item stays open, e.g.
# "without a CLI the item stays open as runtime unverified".
KEEPS_OPEN_RE = re.compile(r"\bstays? open as runtime unverified\b")


def test_acceptance_has_no_escape_hatches() -> None:
    bad = []
    for item_id, *_, body in _items():
        for line in body.splitlines():
            if "Acceptance:" not in line:
                continue
            if ESCAPE_HATCH_RE.search(line):
                bad.append(item_id)
            elif line.count("unverified") != len(KEEPS_OPEN_RE.findall(line)):
                bad.append(item_id)  # runtime gaps must keep the item open
    assert not bad, f"acceptance criteria that let 'unverified' count as done: {bad}"


def test_every_open_item_has_acceptance() -> None:
    missing = [
        item_id
        for item_id, *_, body in _items()
        if body.startswith("- [ ]") and "Acceptance:" not in body
    ]
    assert not missing, f"open items without acceptance criteria: {missing}"


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
    assert len(agents.splitlines()) <= 120  # one target, stated in VISION.md and ADR 0004
    assert len(agents.encode()) < 32 * 1024  # Codex project_doc_max_bytes default
    assert "@AGENTS.md" in (REPO_ROOT / "CLAUDE.md").read_text()


ADR_DIR = REPO_ROOT / "docs" / "adr"
ADR_FILES = sorted(p for p in ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md") if not p.name.startswith("0000"))
STATUS_RE = re.compile(r"^- Status: (\w+)", re.MULTILINE)
HOST_RE = re.compile(r"\b(?:[a-z0-9-]+\.)+(?:com|example|io|dev|net|org)\b")
PATH_RE = re.compile(r"`([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.{}-]+)+)`")


def _status(path: Path) -> str:
    match = STATUS_RE.search(path.read_text())
    assert match, f"{path.name} has no '- Status:' line"
    return match.group(1)


def test_adr_index_matches_adr_status() -> None:
    index = (ADR_DIR / "README.md").read_text()
    for path in ADR_FILES:
        row = next((line for line in index.splitlines() if f"({path.name})" in line), None)
        assert row, f"{path.name} missing from docs/adr/README.md"
        assert row.rstrip(" |").split("|")[-1].strip().startswith(_status(path)), path.name


@pytest.mark.parametrize("path", ADR_FILES, ids=lambda p: p.name)
def test_accepted_adrs_only_claim_what_is_in_the_tree(path: Path) -> None:
    """An Accepted ADR may only name repo paths that exist and MCP hosts the plugin uses."""
    if _status(path) != "Accepted":
        return
    text = path.read_text()
    plugin_hosts = set(HOST_RE.findall((REPO_ROOT / ".mcp.json").read_text()))
    adr_hosts = {h for h in HOST_RE.findall(text) if "jdad" in h}
    assert adr_hosts <= plugin_hosts, f"hosts not in .mcp.json: {adr_hosts - plugin_hosts}"
    missing = [
        rel
        for rel in PATH_RE.findall(text)
        if "{" not in rel and not (REPO_ROOT / rel).exists()
    ]
    assert not missing, f"paths named in an Accepted ADR but absent: {missing}"
