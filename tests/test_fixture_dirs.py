"""Every directory under tests/fixtures/ holds at least one file.

Git tracks files, not directories: an empty fixture directory exists in the
author's working copy and not in a fresh clone. tests/fixtures/review/sources/
was one, and 14 tests passed locally but failed in CI on d3e2701 (Checker on
#38, JON-1393 item 12). Put a `.gitkeep` in a directory that must stay empty.
"""

from __future__ import annotations

from pathlib import Path

import pytest

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


def check_fixtures(root: Path) -> None:
    """The guard itself: the root exists and has fixture dirs, and none of them is empty.

    Without the first two checks a missing or empty tests/fixtures/ would pass
    (Checker on #39, JON-1393 item 18)."""
    assert root.is_dir(), f"{root} is missing"
    assert any(p.is_dir() and p.name not in IGNORED for p in root.iterdir()), f"{root} has no fixture directories"
    empty = empty_dirs(root)
    assert not empty, f"git won't track these empty fixture dirs; add a .gitkeep to each: {empty}"


def test_no_fixture_directory_is_empty() -> None:
    check_fixtures(FIXTURES)


@pytest.mark.parametrize(
    ("layout", "message"),
    [
        ([], "is missing"),
        (["fixtures/"], "has no fixture directories"),
        (["fixtures/__pycache__/"], "has no fixture directories"),
        (["fixtures/README.md"], "has no fixture directories"),
        (["fixtures/review/x.md", "fixtures/review/sources/"], "add a .gitkeep"),
    ],
    ids=["missing", "empty", "only-a-cache-dir", "only-a-file", "an-empty-subdir"],
)
def test_the_guard_fails_on_a_missing_or_empty_root(tmp_path: Path, layout: list[str], message: str) -> None:
    for rel in layout:
        target = tmp_path / rel
        if rel.endswith("/"):
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("x")
    with pytest.raises(AssertionError, match=message):
        check_fixtures(tmp_path / "fixtures")


@pytest.mark.parametrize("cache", sorted(IGNORED))
def test_every_ignored_cache_dir_is_ignored(tmp_path: Path, cache: str) -> None:
    """Checker on #39, mutant H55: the whole ignore list, not just __pycache__.

    An empty cache dir isn't reported, and a file that lives only in a cache dir
    doesn't make its parent count as non-empty."""
    assert IGNORED == {"__pycache__", ".pytest_cache", ".ruff_cache"}
    (tmp_path / "kb" / "real").mkdir(parents=True)
    (tmp_path / "kb" / "real" / "a.md").write_text("x")
    (tmp_path / "kb" / "real" / cache).mkdir()
    (tmp_path / "kb" / "only_cache" / cache).mkdir(parents=True)
    (tmp_path / "kb" / "only_cache" / cache / "x").write_bytes(b"")
    assert empty_dirs(tmp_path) == ["kb/only_cache"]


def test_the_check_finds_an_empty_directory(tmp_path: Path) -> None:
    (tmp_path / "kb" / "practices").mkdir(parents=True)
    (tmp_path / "kb" / "practices" / "a.md").write_text("x")
    (tmp_path / "kb" / "sources").mkdir()
    (tmp_path / "kb" / "deep" / "er").mkdir(parents=True)
    (tmp_path / "kb" / "__pycache__").mkdir()
    (tmp_path / "kb" / "only_cache" / "__pycache__").mkdir(parents=True)
    (tmp_path / "kb" / "only_cache" / "__pycache__" / "x.pyc").write_bytes(b"")
    assert empty_dirs(tmp_path) == ["kb/deep", "kb/deep/er", "kb/only_cache", "kb/sources"]
