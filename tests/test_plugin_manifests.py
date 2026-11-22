from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_marketplace_and_plugin_manifests() -> None:
    marketplace = json.loads((REPO_ROOT / ".claude-plugin/marketplace.json").read_text())
    plugin = json.loads((REPO_ROOT / ".claude-plugin/plugin.json").read_text())
    assert marketplace["name"] == "jdad"
    assert marketplace["owner"]["name"]
    assert marketplace["plugins"][0]["name"] == "jdad"
    assert marketplace["plugins"][0]["source"] == "./"
    assert plugin["name"] == "jdad"
    assert plugin["version"]
    mcp = json.loads((REPO_ROOT / ".mcp.json").read_text())
    server = mcp["mcpServers"]["jdad"]
    assert server["url"] == "https://jdad-mcp.jondevs.com/mcp"
    assert server["headers"]["Authorization"] == "Bearer ${JDAD_TOKEN}"
    assert "CF-Access-Client-Id" not in server["headers"]
    assert "CF-Access-Client-Secret" not in server["headers"]
    command = (REPO_ROOT / "commands/jdad.md").read_text()
    assert "/jdad plan" in command or "plan" in command
    assert "Daisy" in command
    skill = (REPO_ROOT / "skills/jdad-performance/SKILL.md").read_text()
    assert "Skeleton" in skill or "N+1" in skill or "performance" in skill.lower()


def test_marketplace_git_sources_are_pinned_by_sha() -> None:
    """Any non-relative plugin source must pin a 40-hex commit (ROADMAP P7.2 prerequisite)."""
    import json
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    marketplace = json.loads((root / ".claude-plugin/marketplace.json").read_text())
    unpinned = []
    for entry in marketplace.get("plugins") or []:
        source = entry.get("source")
        if isinstance(source, str) and source.startswith("./"):
            continue  # this repo itself; main is the trust boundary
        sha = source.get("sha") if isinstance(source, dict) else None
        if not (isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha)):
            unpinned.append(entry.get("name"))
    assert not unpinned, f"plugin sources without a pinned sha: {unpinned}"
