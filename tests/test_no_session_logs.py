"""Claude Code session transcripts and agent logs never go in the repo (Jon, 2026-11-22)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
# Markers that appear on every line of a Claude Code session transcript.
MARKERS = ('"sessionId"', '"parentUuid"')
# Transcripts are .jsonl on disk; exports, copies and pastes show up as .json,
# .ndjson, .log, .txt, .md or .yaml. Suffixes are compared in lower case.
LOG_SUFFIXES = {".jsonl", ".json", ".ndjson", ".log", ".txt", ".md", ".yaml", ".yml"}


def tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "--no-optional-locks", "ls-files", "-z"], cwd=REPO_ROOT, capture_output=True, check=True
    ).stdout.decode()
    return [REPO_ROOT / name for name in out.split("\0") if name]


def looks_like_session_log(path: Path) -> bool:
    """Both markers anywhere in the file (a pasted excerpt can start late)."""
    if path.suffix.lower() not in LOG_SUFFIXES or not path.is_file():
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    return all(marker in text for marker in MARKERS)


def is_agent_log_path(relpath: Path) -> bool:
    """Paths where agent memory and session logs live (.remember/, .claude/projects/)."""
    return relpath.parts[:1] == (".remember",) or relpath.parts[:2] == (".claude", "projects")


def test_no_tracked_session_transcripts() -> None:
    offenders = [
        p.relative_to(REPO_ROOT).as_posix()
        for p in tracked_files()
        if looks_like_session_log(p) or is_agent_log_path(p.relative_to(REPO_ROOT))
    ]
    assert not offenders, f"session transcripts or agent logs are tracked: {offenders}"


def test_detector_recognises_a_session_line(tmp_path: Path) -> None:
    log = tmp_path / "abc.jsonl"
    log.write_text('{"parentUuid":null,"sessionId":"x","type":"user"}\n')
    assert looks_like_session_log(log)
    exported = tmp_path / "session.json"
    exported.write_text('[{"parentUuid": null, "sessionId": "x", "type": "user"}]')
    assert looks_like_session_log(exported)
    data = tmp_path / "data.jsonl"
    data.write_text('{"id": 1}\n')
    assert not looks_like_session_log(data)


def test_gitignore_covers_session_paths() -> None:
    ignore = (REPO_ROOT / ".gitignore").read_text().splitlines()
    assert ".claude/projects/" in ignore and ".remember/" in ignore


# Checker 12B (JON-1360): copies in other formats, upper-case suffixes, markers
# past the first 4 KB, and the path rules.
SESSION_LINE = '{"parentUuid":null,"sessionId":"x","type":"user"}'


@pytest.mark.parametrize("name", ["notes.md", "session.yaml", "session.yml", "ABC.JSONL", "Export.Json"])
def test_detector_covers_other_formats_and_any_case(tmp_path: Path, name: str) -> None:
    copy = tmp_path / name
    copy.write_text(f"Pasted transcript:\n\n{SESSION_LINE}\n")
    assert looks_like_session_log(copy)


def test_detector_finds_markers_past_the_first_4kb(tmp_path: Path) -> None:
    log = tmp_path / "late.jsonl"
    log.write_text('{"id": 1}\n' * 600 + SESSION_LINE + "\n")
    assert log.stat().st_size > 4096
    assert looks_like_session_log(log)


def test_detector_needs_both_markers(tmp_path: Path) -> None:
    half = tmp_path / "half.md"
    half.write_text('Only "sessionId" is named here.\n')
    assert not looks_like_session_log(half)


@pytest.mark.parametrize(
    ("relpath", "flagged"),
    [
        (".remember/now.md", True),
        (".remember/today-2026-11-23.md", True),
        (".claude/projects/x/abc.jsonl", True),
        (".claude/settings.json", False),
        ("docs/remember.md", False),
        ("src/projects/x.py", False),
    ],
)
def test_agent_log_paths_are_flagged(relpath: str, flagged: bool) -> None:
    assert is_agent_log_path(Path(relpath)) is flagged
