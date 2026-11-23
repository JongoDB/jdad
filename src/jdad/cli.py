"""`jdad` command line: repo tooling (the MCP server is `jdad-mcp`).

- `jdad lint-kb`: content checks on practices/, sources/, skills/ and commands/.
- `jdad build [--check]`: compile catalog/ into skills/, generated/agents-skills/
  and generated/cursor-rules/.
- `jdad freshness [--today DATE] [--strict]`: sources over a year old whose
  topic cites a newer source.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from jdad import build as build_mod
from jdad.kb import resolve_kb_root
from jdad.lint import lint_kb


def _lint_kb(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve() if args.root else resolve_kb_root()
    try:
        findings = lint_kb(root)
    except ValueError as exc:
        print(f"jdad lint-kb: {exc}", file=sys.stderr)
        return 2
    for finding in findings:
        print(finding.format())
    if findings:
        print(f"jdad lint-kb: {len(findings)} finding(s) in {root}", file=sys.stderr)
        return 1
    print(f"jdad lint-kb: ok ({root})")
    return 0


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


def _freshness(args: argparse.Namespace) -> int:
    from jdad.freshness import freshness_report

    root = Path(args.root).resolve() if args.root else resolve_kb_root()
    today = date.fromisoformat(args.today) if args.today else date.today()
    lines = freshness_report(root, today)
    for line in lines:
        print(line)
    if not lines:
        print(f"jdad freshness: no stale sources as of {today}")
    return 1 if lines and args.strict else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jdad", description="JDAD repo tooling.")
    sub = parser.add_subparsers(dest="command", required=True)
    lint = sub.add_parser("lint-kb", help="Check practices/, sources/, skills/ and commands/ for unsafe content.")
    lint.add_argument("--root", help="KB root (default: KB_ROOT, then this checkout).")
    lint.set_defaults(func=_lint_kb)
    build = sub.add_parser("build", help="compile catalog/ into skills/, generated/agents-skills/ and generated/cursor-rules/")
    build.add_argument("--check", action="store_true", help="write nothing; fail if any output is out of date")
    build.add_argument("--root", default=".", help="repo root (default: the current directory)")
    build.set_defaults(func=_build)
    fresh = sub.add_parser("freshness", help="list sources over a year old whose topic cites a newer source")
    fresh.add_argument("--root", help="KB root (default: KB_ROOT, then this checkout).")
    fresh.add_argument("--today", help="date to measure from, YYYY-MM-DD (default: today)")
    fresh.add_argument("--strict", action="store_true", help="exit 1 when anything is reported")
    fresh.set_defaults(func=_freshness)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
