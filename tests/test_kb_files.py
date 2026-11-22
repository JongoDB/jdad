"""The server never serves a symlink, a file outside the KB, or an oversized file.

Checker on PR #8: with the lint alone, a symlinked practice still returned
/etc/hosts through get_practice and the listing tools at runtime.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from jdad.kb import MAX_KB_FILE_BYTES, KnowledgeBase, read_kb_file
from jdad.lint import lint_kb

GOOD = "# Good\n## Backend [backend]\n- Paginate every list endpoint. (src: x #1)\n"


@pytest.fixture
def secret(tmp_path: Path) -> Path:
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "secret.md"
    target.write_text("# Secret\n## Leak [backend]\n- OUTSIDE-THE-KB marker\n")
    return target


def make_kb(tmp_path: Path) -> Path:
    root = tmp_path / "kb"
    (root / "practices").mkdir(parents=True)
    (root / "sources").mkdir()
    (root / "practices" / "good.md").write_text(GOOD)
    (root / "sources" / "2026-01-01-real.md").write_text("# Real\n- Link: https://example.com\n")
    return root


def everything(kb: KnowledgeBase) -> str:
    """Text from every tool path that reads files."""
    parts = [str(kb.list_topics()), str(kb.list_sources()), kb.get_checklist([])]
    parts.append(str(kb.search_practices("marker")))
    return "\n".join(parts)


def test_symlinked_practice_is_never_served(tmp_path: Path, secret: Path, caplog: pytest.LogCaptureFixture) -> None:
    root = make_kb(tmp_path)
    (root / "practices" / "link.md").symlink_to(secret)
    kb = KnowledgeBase(root)
    with caplog.at_level(logging.WARNING, logger="jdad.kb"):
        assert "OUTSIDE-THE-KB" not in everything(kb)
        for needle in ("link", "link.md", "lin"):
            with pytest.raises(FileNotFoundError):
                kb.get_practice(needle)
    assert [t["topic"] for t in kb.list_topics()] == ["good"]
    assert "symlink" in caplog.text


def test_symlink_to_etc_hosts_is_refused(tmp_path: Path) -> None:
    """Checker's exact repro."""
    if not Path("/etc/hosts").exists():
        pytest.skip("no /etc/hosts")
    root = make_kb(tmp_path)
    (root / "practices" / "hosts.md").symlink_to("/etc/hosts")
    kb = KnowledgeBase(root)
    with pytest.raises(FileNotFoundError):
        kb.get_practice("hosts")
    assert "hosts" not in [t["topic"] for t in kb.list_topics()]


def test_symlinked_source_is_never_served(tmp_path: Path, secret: Path) -> None:
    root = make_kb(tmp_path)
    (root / "sources" / "2026-01-02-link.md").symlink_to(secret)
    kb = KnowledgeBase(root)
    assert [s["id"] for s in kb.list_sources()] == ["2026-01-01-real"]
    with pytest.raises(FileNotFoundError):
        kb.get_source("2026-01-02-link")
    assert kb.newest_entry_date() == "2026-01-01"


def test_symlinked_directory_is_never_served(tmp_path: Path, secret: Path) -> None:
    root = make_kb(tmp_path)
    (root / "practices" / "good.md").unlink()
    (root / "practices").rmdir()
    (root / "practices").symlink_to(secret.parent, target_is_directory=True)
    kb = KnowledgeBase(root)
    assert kb.list_topics() == []
    with pytest.raises(FileNotFoundError):
        kb.get_practice("secret")


def test_symlinked_parent_inside_the_kb_is_refused(tmp_path: Path) -> None:
    """practices/ pointing at sources/ stays inside the root but isn't practices/."""
    root = make_kb(tmp_path)
    (root / "practices" / "good.md").unlink()
    (root / "practices").rmdir()
    (root / "practices").symlink_to(root / "sources", target_is_directory=True)
    assert KnowledgeBase(root).list_topics() == []


def test_oversized_file_is_refused(tmp_path: Path) -> None:
    root = make_kb(tmp_path)
    big = root / "practices" / "big.md"
    big.write_text("# Big\n## A [backend]\n- " + "x" * (MAX_KB_FILE_BYTES + 1) + "\n")
    kb = KnowledgeBase(root)
    assert [t["topic"] for t in kb.list_topics()] == ["good"]
    with pytest.raises(FileNotFoundError):
        kb.get_practice("big")
    with pytest.raises(FileNotFoundError, match="larger than"):
        read_kb_file(big)
    assert ("size", "practices/big.md") in [(f.check, f.path) for f in lint_kb(root)]


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no FIFOs")
def test_fifo_does_not_hang(tmp_path: Path) -> None:
    root = make_kb(tmp_path)
    os.mkfifo(root / "practices" / "pipe.md")
    kb = KnowledgeBase(root)
    assert [t["topic"] for t in kb.list_topics()] == ["good"]
    with pytest.raises(FileNotFoundError):
        kb.get_practice("pipe")
    with pytest.raises(FileNotFoundError, match="not a regular file"):
        read_kb_file(root / "practices" / "pipe.md")


def test_reader_refuses_a_symlink_swapped_in_after_listing(tmp_path: Path, secret: Path) -> None:
    root = make_kb(tmp_path)
    path = root / "practices" / "good.md"
    listed = KnowledgeBase(root).practice_paths()
    assert listed == [path]
    path.unlink()
    path.symlink_to(secret)
    with pytest.raises(FileNotFoundError, match="symlink"):
        read_kb_file(listed[0])


def test_regular_files_still_resolve_case_insensitively(tmp_path: Path) -> None:
    kb = KnowledgeBase(make_kb(tmp_path))
    assert kb.get_practice("good").startswith("# Good")
    assert kb.get_practice("GOOD").startswith("# Good")
    assert kb.get_practice("practices/good.md").startswith("# Good")
