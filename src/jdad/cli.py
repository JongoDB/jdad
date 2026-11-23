"""`jdad` command line: repo tooling (the MCP server is `jdad-mcp`).

- `jdad lint-kb`: content checks on practices/, sources/, skills/ and commands/.
- `jdad build [--check]`: compile catalog/ into skills/, generated/agents-skills/
  and generated/cursor-rules/.
- `jdad kb dupes [--threshold]`: rule pairs that look like duplicates (a report).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from jdad import build as build_mod
from jdad import dupes as dupes_mod
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


def _kb_dupes(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve() if args.root else resolve_kb_root()
    for line in dupes_mod.report(root, args.threshold):
        print(line)
    return 0  # a report for a human, never a gate


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
    kb = sub.add_parser("kb", help="Reports about the knowledge base.")
    kb_sub = kb.add_subparsers(dest="kb_command", required=True)
    dupes = kb_sub.add_parser("dupes", help="List rule pairs that look like duplicates (always exits 0).")
    dupes.add_argument("--threshold", type=float, default=dupes_mod.THRESHOLD, help=f"cosine cutoff (default {dupes_mod.THRESHOLD})")
    dupes.add_argument("--root", help="KB root (default: KB_ROOT, then this checkout).")
    dupes.set_defaults(func=_kb_dupes)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
