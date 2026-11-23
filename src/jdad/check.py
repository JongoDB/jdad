"""`jdad-mcp --check`: prove the KB loads before it is served.

Runs every read path the MCP tools use, file by file, so one broken file is
named instead of surfacing later as a failed tool call on the live server.
Used by the Dockerfile (on the installed package, i.e. what ships) and so by
deploy/update-docker.sh before it swaps containers.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from jdad.kb import PRACTICES_DIR, SOURCES_DIR, KnowledgeBase, parse_practice


def _try(problems: list[str], label: str, fn: Callable[[], object]) -> None:
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 - report every failure, keep going
        problems.append(f"{label}: {type(exc).__name__}: {exc}")


def check_kb(root: str | Path | None = None) -> tuple[Path | None, list[str]]:
    """Return (kb_root, problems). An empty list means the KB is servable."""
    problems: list[str] = []
    try:
        kb = KnowledgeBase(root)
    except Exception as exc:  # noqa: BLE001
        return None, [f"KB root: {type(exc).__name__}: {exc}"]

    for directory in (PRACTICES_DIR, SOURCES_DIR):
        base = kb.root / directory
        for path in sorted(base.iterdir()):
            rel = f"{directory}/{path.name}"
            if path.is_symlink():
                problems.append(f"{rel}: is a symlink")
                continue
            if not path.is_file() or path.suffix != ".md":
                continue
            try:
                path.read_bytes().decode("utf-8")
            except UnicodeDecodeError as exc:
                problems.append(f"{rel}: not valid UTF-8 ({exc.reason} at byte {exc.start})")
                continue
            except OSError as exc:
                problems.append(f"{rel}: unreadable ({exc.strerror or type(exc).__name__})")
                continue
            if directory == PRACTICES_DIR:
                _try(problems, rel, lambda p=path: parse_practice(p, root=kb.root))

    if problems:
        # The aggregate calls below would only fail again on the same files.
        return kb.root, problems

    _try(problems, "list_topics", kb.list_topics)
    _try(problems, "list_sources", kb.list_sources)
    _try(problems, "get_checklist([])", lambda: kb.get_checklist([]))
    _try(problems, "search_practices", lambda: kb.search_practices("a"))
    _try(problems, "kb_version", kb.version)
    for path in kb.practice_paths():
        _try(problems, f"get_practice({path.stem})", lambda s=path.stem: kb.get_practice(s))
    for path in kb.source_paths():
        _try(problems, f"get_source({path.stem})", lambda s=path.stem: kb.get_source(s))
    if not kb.practice_paths():
        problems.append(f"{PRACTICES_DIR}/: no practice files")
    return kb.root, problems


def run_check(root: str | Path | None = None) -> int:
    kb_root, problems = check_kb(root)
    for problem in problems:
        print(f"jdad-mcp --check: {problem}")
    if problems:
        print(f"jdad-mcp --check: FAILED, {len(problems)} problem(s) in {kb_root}")
        return 1
    print(f"jdad-mcp --check: ok ({kb_root})")
    return 0
