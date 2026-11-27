"""Every directory under tests/fixtures/ holds at least one file.

Git tracks files, not directories: an empty fixture directory exists in the
author's working copy and not in a fresh clone. tests/fixtures/review/sources/
was one, and 14 tests passed locally but failed in CI on d3e2701 (Checker on
#38, JON-1393 item 12). Put a `.gitkeep` in a directory that must stay empty.
"""

from __future__ import annotations

from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
IGNORED = {"__pycache__", ".pytest_cache", ".ruff_cache"}


def empty_dirs(root: Path) -> list[str]:
    """Directories under root (ignoring cache dirs) with no file anywhere below them."""
    found = []
    for path in sorted(root.rglob("*")):
        if not path.is_dir() or IGNORED & set(path.relative_to(root).parts):
            continue
        if not any(p.is_file() for p in path.rglob("*") if not IGNORED & set(p.relative_to(root).parts)):
            found.append(path.relative_to(root).as_posix())
    return found


def test_no_fixture_directory_is_empty() -> None:
    empty = empty_dirs(FIXTURES)
    assert not empty, f"git won't track these empty fixture dirs; add a .gitkeep to each: {empty}"


def test_the_check_finds_an_empty_directory(tmp_path: Path) -> None:
    (tmp_path / "kb" / "practices").mkdir(parents=True)
    (tmp_path / "kb" / "practices" / "a.md").write_text("x")
    (tmp_path / "kb" / "sources").mkdir()
    (tmp_path / "kb" / "deep" / "er").mkdir(parents=True)
    (tmp_path / "kb" / "__pycache__").mkdir()
    (tmp_path / "kb" / "only_cache" / "__pycache__").mkdir(parents=True)
    (tmp_path / "kb" / "only_cache" / "__pycache__" / "x.pyc").write_bytes(b"")
    assert empty_dirs(tmp_path) == ["kb/deep", "kb/deep/er", "kb/only_cache", "kb/sources"]
