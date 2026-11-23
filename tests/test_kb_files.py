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


def test_one_bad_file_does_not_break_listings(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Checker on #8 (M3's other half): a non-UTF-8 practice or source used to
    make list_topics, get_checklist and list_sources raise."""
    root = make_kb(tmp_path)
    (root / "practices" / "bad.md").write_bytes(b"# Bad\n\xff\xfe\n")
    (root / "sources" / "2026-01-02-bad.md").write_bytes(b"# Bad\n\xff\n")
    kb = KnowledgeBase(root)
    with caplog.at_level(logging.WARNING, logger="jdad.kb"):
        assert [t["topic"] for t in kb.list_topics()] == ["good"]
        assert "Paginate" in kb.get_checklist([])
        assert kb.search_practices("Paginate")
        assert [s["id"] for s in kb.list_sources()] == ["2026-01-01-real"]
    assert "skipping practice bad.md" in caplog.text
    assert "skipping source 2026-01-02-bad.md" in caplog.text
    with pytest.raises(UnicodeDecodeError):
        kb.get_practice("bad")  # asking for it directly still fails loudly


# ---- JON-1352: the resolve checks are the second line of defense ----
# In normal operation the symlink checks catch everything first, so these
# simulate a directory or file swapped for a symlink between the two checks.


def test_directory_swapped_to_a_symlink_after_the_check_is_refused(
    tmp_path: Path, secret: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from jdad import kb as kb_mod

    root = tmp_path / "kb"
    root.mkdir()
    (root / "practices").symlink_to(secret.parent, target_is_directory=True)
    real_is_symlink = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda p: False if p.name == "practices" else real_is_symlink(p))
    assert kb_mod.kb_markdown_files(root, root / "practices") == []


def test_file_swapped_to_a_symlink_after_the_check_is_refused(
    tmp_path: Path, secret: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    from jdad import kb as kb_mod

    root = tmp_path / "kb"
    (root / "practices").mkdir(parents=True)
    (root / "practices" / "leak.md").symlink_to(secret)
    real_lstat = Path.lstat
    monkeypatch.setattr(Path, "lstat", lambda p: os.stat(p) if p.name == "leak.md" else real_lstat(p))
    assert kb_mod.kb_markdown_files(root, root / "practices") == []
