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
    assert server["url"] == "http://jdad.local:8765/mcp"
    assert server["headers"]["Authorization"] == "Bearer ${JDAD_TOKEN}"
    command = (REPO_ROOT / "commands/jdad.md").read_text()
    assert "/jdad plan" in command or "plan" in command
    assert "Daisy" in command
    skill = (REPO_ROOT / "skills/jdad-performance/SKILL.md").read_text()
    assert "Skeleton" in skill or "N+1" in skill or "performance" in skill.lower()
