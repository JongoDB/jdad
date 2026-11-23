"""`jdad` command line: repo tooling (the MCP server is `jdad-mcp`)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jdad", description="JDAD repo tooling.")
    sub = parser.add_subparsers(dest="command", required=True)
    lint = sub.add_parser("lint-kb", help="Check practices/, sources/, skills/ and commands/ for unsafe content.")
    lint.add_argument("--root", help="KB root (default: KB_ROOT, then this checkout).")
    lint.set_defaults(func=_lint_kb)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
