"""Read-only loader and search for the agentic coding knowledge base."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

PRACTICES_DIR = "practices"
SOURCES_DIR = "sources"

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_TRAILING_TAG_RE = re.compile(r"\s*\[([a-z][a-z0-9-]*)\]\s*$")
_BULLET_RE = re.compile(r"^[-*]\s+")
_LINK_RE = re.compile(r"(?im)^(?:-\s*)?Link:\s*(\S+)")
_DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def resolve_kb_root(explicit: str | Path | None = None) -> Path:
    """Locate the KB root (the directory that contains practices/ and sources/).

    Order: explicit argument, KB_ROOT env, walk from cwd and this file to a
    repo checkout, then bundled package data shipped in the wheel.
    """
    if explicit is not None:
        return _require_root(Path(explicit).expanduser().resolve())

    env = os.environ.get("KB_ROOT")
    if env:
        return _require_root(Path(env).expanduser().resolve())

    for start in (Path.cwd(), Path(__file__).resolve()):
        for candidate in (start, *start.parents):
            if _is_kb_root(candidate):
                return candidate.resolve()

    bundled = Path(__file__).resolve().parent / "data"
    if _is_kb_root(bundled):
        return bundled

    raise FileNotFoundError(
        "Could not locate the knowledge base. Set KB_ROOT to the directory "
        "that contains practices/ and sources/."
    )



def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run git without optional locks so reads cannot race a checkout or refresh the index."""
    return subprocess.run(
        ["git", "--no-optional-locks", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )


def _is_kb_root(path: Path) -> bool:
    return (path / PRACTICES_DIR).is_dir() and (path / SOURCES_DIR).is_dir()


def _require_root(path: Path) -> Path:
    if not _is_kb_root(path):
        raise FileNotFoundError(
            f"KB root {path} is missing {PRACTICES_DIR}/ or {SOURCES_DIR}/"
        )
    return path


def split_heading_tags(text: str) -> tuple[str, list[str]]:
    """Pull trailing [tag] markers off a heading, leaving the visible title."""
    tags: list[str] = []
    title = text.rstrip()
    while True:
        match = _TRAILING_TAG_RE.search(title)
        if not match:
            break
        tags.append(match.group(1))
        title = title[: match.start()]
    tags.reverse()
    return title.strip(), tags


def first_heading(text: str, level: int | None = 1) -> str | None:
    for line in text.splitlines():
        match = _HEADING_RE.match(line.strip())
        if not match:
            continue
        if level is not None and len(match.group(1)) != level:
            continue
        title, _ = split_heading_tags(match.group(2))
        return title or None
    return None


def extract_link(text: str) -> str | None:
    match = _LINK_RE.search(text)
    return match.group(1).rstrip(").,") if match else None


def extract_bullets(body: str) -> list[str]:
    bullets: list[str] = []
    for line in body.splitlines():
        if _BULLET_RE.match(line):
            bullets.append(_BULLET_RE.sub("", line).strip())
    return bullets


@dataclass(frozen=True)
class Section:
    heading: str
    level: int
    tags: tuple[str, ...]
    body: str

    @property
    def bullets(self) -> list[str]:
        return extract_bullets(self.body)


@dataclass(frozen=True)
class PracticeDoc:
    topic: str
    relpath: str
    title: str
    preamble: str
    sections: tuple[Section, ...]
    text: str

    @property
    def tags(self) -> list[str]:
        seen: list[str] = []
        for section in self.sections:
            for tag in section.tags:
                if tag not in seen:
                    seen.append(tag)
        return seen

    @property
    def headings(self) -> list[str]:
        return [section.heading for section in self.sections]


def parse_practice(path: Path, *, root: Path) -> PracticeDoc:
    text = path.read_text(encoding="utf-8")
    title = first_heading(text, 1) or path.stem
    sections: list[Section] = []
    preamble_lines: list[str] = []
    current: dict | None = None
    seen_h1 = False

    def close() -> None:
        nonlocal current
        if current is not None:
            sections.append(
                Section(
                    heading=current["heading"],
                    level=current["level"],
                    tags=tuple(current["tags"]),
                    body="\n".join(current["body"]).strip("\n"),
                )
            )
            current = None

    for raw in text.splitlines():
        match = _HEADING_RE.match(raw)
        if match:
            level = len(match.group(1))
            heading, tags = split_heading_tags(match.group(2))
            if level == 1 and not seen_h1:
                seen_h1 = True
                continue
            if level >= 2:
                close()
                current = {
                    "heading": heading,
                    "level": level,
                    "tags": tags,
                    "body": [],
                }
                continue
        if current is None:
            preamble_lines.append(raw)
        else:
            current["body"].append(raw)

    close()
    preamble = "\n".join(preamble_lines).strip("\n").strip()
    relpath = path.resolve().relative_to(root.resolve()).as_posix()
    return PracticeDoc(
        topic=path.stem,
        relpath=relpath,
        title=title,
        preamble=preamble,
        sections=tuple(sections),
        text=text,
    )


class KnowledgeBase:
    """Filesystem-backed, read-only view of practices/ and sources/."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = resolve_kb_root(root)

    @property
    def practices_dir(self) -> Path:
        return self.root / PRACTICES_DIR

    @property
    def sources_dir(self) -> Path:
        return self.root / SOURCES_DIR

    def practice_paths(self) -> list[Path]:
        return sorted(self.practices_dir.glob("*.md"))

    def source_paths(self) -> list[Path]:
        return sorted(self.sources_dir.glob("*.md"))

    def practices(self) -> list[PracticeDoc]:
        return [parse_practice(path, root=self.root) for path in self.practice_paths()]

    def list_topics(self) -> list[dict]:
        topics = []
        for doc in self.practices():
            topics.append(
                {
                    "topic": doc.topic,
                    "title": doc.title,
                    "file": doc.relpath,
                    "tags": doc.tags,
                    "headings": doc.headings,
                }
            )
        return topics

    def get_practice(self, topic: str) -> str:
        return self._resolve_file(self.practices_dir, topic, kind="practice").read_text(
            encoding="utf-8"
        )

    def list_sources(self) -> list[dict]:
        items = []
        for path in self.source_paths():
            text = path.read_text(encoding="utf-8")
            items.append(
                {
                    "id": path.stem,
                    "file": path.relative_to(self.root).as_posix(),
                    "title": first_heading(text, 1) or path.stem,
                    "link": extract_link(text),
                }
            )
        return items

    def get_source(self, source_id: str) -> str:
        return self._resolve_file(self.sources_dir, source_id, kind="source").read_text(
            encoding="utf-8"
        )

    def search_practices(self, query: str, tag: str | None = None) -> list[dict]:
        needle = query.strip().lower()
        if not needle:
            return []
        wanted = tag.strip().lower() if tag and tag.strip() else None
        hits: list[dict] = []
        for doc in self.practices():
            if wanted is None:
                intro = f"{doc.title}\n{doc.preamble}".lower()
                if needle in intro:
                    hits.append(
                        {
                            "topic": doc.topic,
                            "file": doc.relpath,
                            "heading": doc.title,
                            "tags": doc.tags,
                            "body": doc.preamble,
                        }
                    )
            for section in doc.sections:
                if wanted and wanted not in {t.lower() for t in section.tags}:
                    continue
                haystack = f"{section.heading}\n{' '.join(section.tags)}\n{section.body}"
                if needle in haystack.lower():
                    hits.append(
                        {
                            "topic": doc.topic,
                            "file": doc.relpath,
                            "heading": section.heading,
                            "tags": list(section.tags),
                            "body": section.body.strip(),
                        }
                    )
        return hits

    def get_checklist(self, tags: list[str] | None = None) -> str:
        wanted = {t.strip().lower() for t in (tags or []) if t and t.strip()}
        blocks: list[str] = []
        for doc in self.practices():
            matched: list[Section] = []
            for section in doc.sections:
                section_tags = {t.lower() for t in section.tags}
                if wanted and not (section_tags & wanted):
                    continue
                if section.bullets:
                    matched.append(section)
            if not matched:
                continue
            lines = [f"# {doc.title}", f"Topic: {doc.topic}"]
            if wanted:
                lines.append("Tags: " + ", ".join(sorted(wanted)))
            lines.append("")
            for section in matched:
                suffix = " ".join(f"[{t}]" for t in section.tags)
                heading = f"## {section.heading}"
                if suffix:
                    heading = f"{heading} {suffix}"
                lines.append(heading)
                for bullet in section.bullets:
                    lines.append(f"- {bullet}")
                lines.append("")
            blocks.append("\n".join(lines).rstrip())
        if not blocks:
            if wanted:
                return (
                    "No matching practice rules for tags: "
                    + ", ".join(sorted(wanted))
                    + ".\n"
                )
            return "No practice rules found.\n"
        return "\n\n".join(blocks) + "\n"


    def version(self) -> dict:
        """Git SHA of the checkout plus the date of the newest source entry."""
        sha, dirty = self._git_sha()
        newest = self.newest_entry_date()
        display = sha
        if dirty and sha != "unknown":
            display = f"{sha}-dirty"
        if newest:
            display = f"{display} ({newest})"
        return {
            "sha": sha,
            "dirty": dirty,
            "newest_entry": newest,
            "display": display,
        }

    def newest_entry_date(self) -> str | None:
        dates: list[str] = []
        for path in [*self.source_paths(), *self.practice_paths()]:
            match = _DATE_PREFIX_RE.match(path.name)
            if match:
                dates.append(match.group(1))
        return max(dates) if dates else None

    def _git_root(self) -> Path | None:
        for candidate in (self.root, *self.root.parents):
            if (candidate / ".git").exists():
                return candidate
        return None

    def _git_sha(self) -> tuple[str, bool]:
        baked = os.environ.get("JDAD_GIT_SHA", "").strip()
        if baked and baked != "unknown":
            # Image builds bake the checkout SHA; prefer it over a missing .git.
            return baked, False
        git_root = self._git_root()
        if git_root is None:
            return "unknown", False
        try:
            sha = _git(["rev-parse", "HEAD"], git_root).stdout.strip()
            dirty = bool(_git(["status", "--porcelain"], git_root).stdout.strip())
            return sha or "unknown", dirty
        except (OSError, subprocess.SubprocessError):
            return "unknown", False

    def _resolve_file(self, directory: Path, needle: str, *, kind: str) -> Path:
        directory = directory.resolve()
        if not needle or not str(needle).strip():
            raise FileNotFoundError(f"No {kind} id provided")
        raw = str(needle).strip().replace("\\", "/")
        name = Path(raw).name
        stem = name.removesuffix(".md")
        if not stem or stem in {".", ".."}:
            raise FileNotFoundError(f"Invalid {kind} id {needle!r}")

        for candidate in (directory / f"{stem}.md", directory / name):
            resolved = candidate.resolve()
            if resolved.is_file() and resolved.parent == directory:
                return resolved

        matches = sorted(
            path
            for path in directory.glob("*.md")
            if stem.lower() in path.stem.lower() or path.stem.lower() in stem.lower()
        )
        if len(matches) == 1:
            return matches[0]
        available = ", ".join(path.stem for path in self._sorted_md(directory)) or "(none)"
        if len(matches) > 1:
            names = ", ".join(path.stem for path in matches)
            raise FileNotFoundError(
                f"Ambiguous {kind} id {needle!r}; matches: {names}. Available: {available}"
            )
        raise FileNotFoundError(
            f"Unknown {kind} {needle!r}. Available: {available}"
        )

    @staticmethod
    def _sorted_md(directory: Path) -> list[Path]:
        return sorted(directory.glob("*.md"))
