"""Text checks on the GitHub Actions workflows (no YAML dependency)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WORKFLOWS = sorted((Path(__file__).resolve().parents[1] / ".github" / "workflows").glob("*.yml"))


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_actions_are_pinned_to_full_shas(path: Path) -> None:
    for line in path.read_text().splitlines():
        match = re.search(r"uses:\s*([^\s#]+)", line)
        if match and not match.group(1).startswith("./"):
            assert re.search(r"@[0-9a-f]{40}$", match.group(1)), f"{path.name}: unpinned {match.group(1)}"


def _top_level_permissions(text: str) -> list[str]:
    """The top-level `permissions:` line plus its indented children."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("permissions:"))
    block = [lines[start]]
    for line in lines[start + 1 :]:
        if not line.startswith((" ", "\t")):
            break
        block.append(line)
    return block


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_token_permissions_are_minimal(path: Path) -> None:
    block = [line.strip() for line in _top_level_permissions(path.read_text())]
    assert block in (["permissions: {}"], ["permissions:", "contents: read"]), f"{path.name}: {block}"


def test_uptime_check_is_safe_while_private() -> None:
    text = (WORKFLOWS[0].parent / "uptime.yml").read_text()
    assert "permissions: {}" in text
    assert "if: ${{ !github.event.repository.private }}" in text
    assert "secrets." not in text
    assert "uses:" not in text
    assert "https://jdad-mcp.jondevs.com/healthz" in text
