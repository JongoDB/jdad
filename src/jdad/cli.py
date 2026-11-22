"""The `jdad` command (developer tooling; the MCP server is `jdad-mcp`)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from jdad import build as build_mod


def _build(args: argparse.Namespace) -> int:
    root = Path(args.root)
    try:
        if args.check:
            problems = build_mod.check(root)
            for problem in problems:
                print(problem)
            if problems:
                print("jdad build --check: outputs are out of date; run `uv run jdad build`", file=sys.stderr)
                return 1
            print("jdad build --check: ok")
            return 0
        for line in build_mod.build(root) or ["nothing to do"]:
            print(line)
        return 0
    except build_mod.BuildError as exc:
        print(f"jdad build: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jdad", description="JDAD developer tooling")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="compile catalog/ into skills/, generated/agents-skills/ and generated/cursor-rules/")
    build.add_argument("--check", action="store_true", help="write nothing; fail if any output is out of date")
    build.add_argument("--root", default=".", help="repo root (default: the current directory)")
    build.set_defaults(func=_build)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
