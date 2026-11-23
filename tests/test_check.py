"""`jdad-mcp --check`: exit 0 on a servable KB, 1 with the broken file named."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from jdad.check import check_kb
from jdad.server import main

REPO_ROOT = Path(__file__).resolve().parents[1]


def make_kb(root: Path) -> Path:
    (root / "practices").mkdir(parents=True)
    (root / "sources").mkdir()
    (root / "practices" / "ok.md").write_text("# Ok\n## A [backend]\n- rule (src: x #1)\n")
    (root / "sources" / "2026-01-01-x.md").write_text("# X\n- Link: https://example.com\n")
    return root


def run_main(monkeypatch: pytest.MonkeyPatch, root: Path) -> int:
    monkeypatch.setenv("KB_ROOT", str(root))
    with pytest.raises(SystemExit) as excinfo:
        main(["--check"])
    return int(excinfo.value.code)


def test_repo_kb_passes(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    assert run_main(monkeypatch, REPO_ROOT) == 0
    assert "jdad-mcp --check: ok" in capsys.readouterr().out


def test_clean_fixture_passes(tmp_path: Path) -> None:
    assert check_kb(make_kb(tmp_path))[1] == []


def test_non_utf8_practice_fails_and_is_named(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_kb(tmp_path)
    (root / "practices" / "bad.md").write_bytes(b"# Bad\n\xff\xfe\n")
    assert run_main(monkeypatch, root) == 1
    out = capsys.readouterr().out
    assert "practices/bad.md: not valid UTF-8" in out
    assert "FAILED, 1 problem(s)" in out


def test_symlink_fails(tmp_path: Path) -> None:
    root = make_kb(tmp_path)
    (root / "sources" / "2026-01-02-link.md").symlink_to("/etc/hosts")
    problems = check_kb(root)[1]
    assert any(p.startswith("sources/2026-01-02-link.md: is a symlink") for p in problems)


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read a mode-000 file")
def test_unreadable_source_fails(tmp_path: Path) -> None:
    root = make_kb(tmp_path)
    locked = root / "sources" / "2026-01-03-locked.md"
    locked.write_text("# Locked\n")
    locked.chmod(0)
    try:
        problems = check_kb(root)[1]
    finally:
        locked.chmod(0o644)
    assert any(p.startswith("sources/2026-01-03-locked.md: unreadable") for p in problems)


def test_empty_practices_fails(tmp_path: Path) -> None:
    root = make_kb(tmp_path)
    (root / "practices" / "ok.md").unlink()
    assert "practices/: no practice files" in check_kb(root)[1]


def test_missing_kb_root_fails(tmp_path: Path) -> None:
    kb_root, problems = check_kb(tmp_path / "nowhere")
    assert kb_root is None
    assert problems and problems[0].startswith("KB root:")
