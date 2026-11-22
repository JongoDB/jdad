"""Claude Code session transcripts and agent logs never go in the repo (Jon, 2026-11-22)."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# Markers that appear on every line of a Claude Code session transcript.
MARKERS = ('"sessionId"', '"parentUuid"')


def tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "--no-optional-locks", "ls-files", "-z"], cwd=REPO_ROOT, capture_output=True, check=True
    ).stdout.decode()
    return [REPO_ROOT / name for name in out.split("\0") if name]


def looks_like_session_log(path: Path) -> bool:
    if path.suffix != ".jsonl" or not path.is_file():
        return False
    with path.open(encoding="utf-8", errors="replace") as handle:
        head = handle.read(4096)
    return all(marker in head for marker in MARKERS)


def test_no_tracked_session_transcripts() -> None:
    offenders = [
        p.relative_to(REPO_ROOT).as_posix()
        for p in tracked_files()
        if looks_like_session_log(p) or p.relative_to(REPO_ROOT).parts[0] == ".remember"
        or p.relative_to(REPO_ROOT).parts[:2] == (".claude", "projects")
    ]
    assert not offenders, f"session transcripts or agent logs are tracked: {offenders}"


def test_detector_recognises_a_session_line(tmp_path: Path) -> None:
    log = tmp_path / "abc.jsonl"
    log.write_text('{"parentUuid":null,"sessionId":"x","type":"user"}\n')
    assert looks_like_session_log(log)
    data = tmp_path / "data.jsonl"
    data.write_text('{"id": 1}\n')
    assert not looks_like_session_log(data)


def test_gitignore_covers_session_paths() -> None:
    ignore = (REPO_ROOT / ".gitignore").read_text().splitlines()
    assert ".claude/projects/" in ignore and ".remember/" in ignore
