#!/usr/bin/env python3
"""Stop hook: run `./verify --fast` (ruff + pytest) before Claude finishes.

Exit 2 with the failing output on stderr blocks the stop, and Claude sees
why (AGENTS.md R-flow-8). When `stop_hook_active` is true, Claude is
already continuing because of this hook; it stands down then (exit 0 with a
note) so a failure it can't fix never loops. Stdlib only.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

TAIL_LINES = 40
TIMEOUT_S = 280


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        event = {}
    if isinstance(event, dict) and event.get("stop_hook_active"):
        print("stop_verify: already continued once for a failing ./verify --fast; not blocking again", file=sys.stderr)
        return 0
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
    verify = project / "verify"
    if not verify.is_file():
        print(f"stop_verify: no verify script at {verify}; skipping", file=sys.stderr)
        return 0
    try:
        result = subprocess.run(
            [str(verify), "--fast"],
            cwd=project,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print(f"./verify --fast took longer than {TIMEOUT_S}s; fix or speed up the tests before finishing.", file=sys.stderr)
        return 2
    if result.returncode != 0:
        output = (result.stdout + result.stderr).splitlines()[-TAIL_LINES:]
        print("./verify --fast failed (ruff or pytest). Fix it before finishing:", file=sys.stderr)
        print("\n".join(output), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
