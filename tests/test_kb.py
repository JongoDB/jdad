from __future__ import annotations

from pathlib import Path

import pytest

from jdad.kb import KnowledgeBase, resolve_kb_root, split_heading_tags

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_resolve_kb_root_uses_env(kb_root: Path) -> None:
    assert resolve_kb_root() == kb_root.resolve()


def test_split_heading_tags() -> None:
    title, tags = split_heading_tags("Observability and testing [observability] [testing]")
    assert title == "Observability and testing"
    assert tags == ["observability", "testing"]


def test_list_topics_includes_performance() -> None:
    topics = KnowledgeBase(REPO_ROOT).list_topics()
    assert any(item["topic"] == "performance" for item in topics)
    performance = next(item for item in topics if item["topic"] == "performance")
    assert "frontend" in performance["tags"]
    assert "Backend and API" in performance["headings"]


def test_search_and_checklist_filter_by_tag() -> None:
    kb = KnowledgeBase(REPO_ROOT)
    hits = kb.search_practices("N+1", tag="db")
    assert hits
    assert all(hit["heading"] for hit in hits)
    assert any("N+1" in hit["body"] for hit in hits)
    assert not kb.search_practices("N+1", tag="frontend")

    checklist = kb.get_checklist(["frontend"])
    assert "Skeleton loaders" in checklist
    assert "OpenTelemetry" not in checklist
    assert "[frontend]" in checklist


def test_unknown_and_traversal_are_rejected() -> None:
    kb = KnowledgeBase(REPO_ROOT)
    with pytest.raises(FileNotFoundError, match="Unknown practice"):
        kb.get_practice("does-not-exist")
    with pytest.raises(FileNotFoundError):
        kb.get_practice("../README")
    with pytest.raises(FileNotFoundError):
        kb.get_source("../../.gitignore")


def test_source_round_trip() -> None:
    kb = KnowledgeBase(REPO_ROOT)
    sources = kb.list_sources()
    assert sources
    source_id = sources[0]["id"]
    text = kb.get_source(source_id)
    assert "31 items" in text or "Skeleton" in text
    assert "breakingbreach" in source_id


def test_version_includes_sha_and_newest_entry() -> None:
    info = KnowledgeBase(REPO_ROOT).version()
    assert info["sha"]
    assert info["sha"] != "unknown"
    assert info["newest_entry"] == "2026-11-22"
    assert "2026-11-22" in info["display"]
    assert info["sha"] in info["display"]


def test_git_reads_use_no_optional_locks(monkeypatch: pytest.MonkeyPatch) -> None:
    from jdad import kb as kbmod

    seen: list[list[str]] = []

    def fake_run(argv, **kwargs):
        seen.append(list(argv))
        class Result:
            stdout = "deadbeef\n"
        return Result()

    monkeypatch.setattr(kbmod.subprocess, "run", fake_run)
    sha, _dirty = KnowledgeBase(REPO_ROOT)._git_sha()
    assert sha == "deadbeef"
    assert seen
    for argv in seen:
        assert argv[:2] == ["git", "--no-optional-locks"]
