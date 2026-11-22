#!/usr/bin/env python3
"""Fail if packaged/plugin versions are not the same. Used by ./verify."""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    pyproject = tomllib.loads((root / "pyproject.toml").read_text())
    expected = pyproject["project"]["version"]

    init_text = (root / "src/jdad/__init__.py").read_text()
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', init_text, re.MULTILINE)
    if not match:
        print("src/jdad/__init__.py has no __version__", file=sys.stderr)
        return 1
    init_version = match.group(1)

    lock_text = (root / "uv.lock").read_text()
    lock_match = re.search(r'\[\[package\]\]\nname = "jdad"\nversion = "([^"]+)"', lock_text)
    if not lock_match:
        print("uv.lock has no jdad package version", file=sys.stderr)
        return 1
    lock_version = lock_match.group(1)

    plugin = json.loads((root / ".claude-plugin/plugin.json").read_text())
    plugin_version = plugin["version"]

    marketplace = json.loads((root / ".claude-plugin/marketplace.json").read_text())
    found: dict[str, str] = {
        "pyproject.toml": expected,
        "src/jdad/__init__.py": init_version,
        "uv.lock": lock_version,
        ".claude-plugin/plugin.json": plugin_version,
    }
    if "version" in marketplace:
        found["marketplace.json"] = marketplace["version"]
    plugin_entries = marketplace.get("plugins") or []
    for i, entry in enumerate(plugin_entries):
        if "version" in entry:
            found[f"marketplace.json plugins[{i}]"] = entry["version"]
    if not any(name.startswith("marketplace.json") for name in found):
        print("marketplace.json has no version field", file=sys.stderr)
        return 1

    if any(ver != expected for ver in found.values()):
        print(f"FAIL versions differ (expected {expected}):", file=sys.stderr)
        for name, ver in found.items():
            print(f"  {name}: {ver}", file=sys.stderr)
        return 1
    print(f"ok versions={expected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
