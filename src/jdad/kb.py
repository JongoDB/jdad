"""Read-only loader and search for the agentic coding knowledge base."""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("jdad.kb")

PRACTICES_DIR = "practices"
SOURCES_DIR = "sources"

# The tags a practice section may carry (docs/kb-schema.md). P2.3 extends this.
KNOWN_TAGS = ("frontend", "backend", "db", "infra", "observability", "testing")
RULE_ID_RE = re.compile(r"^[a-z][a-z0-9-]*(?:\.[a-z0-9][a-z0-9-]*)+$")
_RULE_ID_SUFFIX_RE = re.compile(r"\s*\{#([^}]*)\}\s*$")
_CITATION_SUFFIX_RE = re.compile(r"\s*\((src:[^()]*|KB addition)\)\s*$", re.IGNORECASE)
_RULE_START_RE = re.compile(r"^[-*]\s+(.*)$")
_NUMBERED_RE = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_NESTED_BULLET_RE = re.compile(r"^\s+[-*+]\s+(.*)$")
_APPLIES_RE = re.compile(r"^\s+applies when:\s*(.*)$", re.IGNORECASE)

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_TRAILING_TAG_RE = re.compile(r"\s*\[([a-z][a-z0-9-]*)\]\s*$")
_BULLET_RE = re.compile(r"^[-*]\s+")
_LINK_RE = re.compile(r"(?im)^(?:-\s*)?Link:\s*(\S+)")
_DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def resolve_kb_root(explicit: str | Path | None = None) -> Path:
    """Locate the KB root (the directory that contains practices/ and sources/).

    Order: explicit argument, KB_ROOT env, the source checkout this module
    was loaded from (``<root>/src/jdad/kb.py``), then the bundled package data
    shipped in the wheel.

    It never walks up from the current directory: a server started inside
    another project must not serve that project's ``practices/`` and
    ``sources/`` as Jon's KB.
    """
    if explicit is not None:
        return _require_root(Path(explicit).expanduser().resolve())

    env = os.environ.get("KB_ROOT")
    if env:
        return _require_root(Path(env).expanduser().resolve())

    checkout = _source_checkout()
    if checkout is not None:
        return checkout

    bundled = Path(__file__).resolve().parent / "data"
    if _is_kb_root(bundled):
        return bundled

    raise FileNotFoundError(
        "Could not locate the knowledge base. Set KB_ROOT to the directory "
        "that contains practices/ and sources/."
    )


def _source_checkout() -> Path | None:
    """The jdad repo this module runs from, if it runs from one (editable install).

    Only the exact layout ``<root>/src/jdad/kb.py`` with ``<root>/pyproject.toml``
    counts. An installed wheel lives under ``site-packages/jdad/``, so a venv
    inside some other project never matches.
    """
    here = Path(__file__).resolve()
    package_dir = here.parent
    src_dir = package_dir.parent
    root = src_dir.parent
    if package_dir.name != "jdad" or src_dir.name != "src":
        return None
    if not (root / "pyproject.toml").is_file() or not _is_kb_root(root):
        return None
    return root


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
class Rule:
    """One KB rule: a `- ` bullet in a tagged section (docs/kb-schema.md)."""

    id: str | None
    text: str
    citation: str | None
    applies_when: str | None
    tags: tuple[str, ...]
    line: int
    last_line: int = 0

    @property
    def spans_lines(self) -> bool:
        return self.last_line > self.line

    @property
    def origin(self) -> str | None:
        if self.citation is None:
            return None
        return "kb-addition" if self.citation.lower() == "kb addition" else "source"

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "tags": list(self.tags),
            "citation": self.citation,
            "origin": self.origin,
            "applies_when": self.applies_when,
        }

    def checklist_line(self) -> str:
        line = f"- {self.id or '(no id)'}: {self.text}"
        if self.citation:
            line += f" ({self.citation})"
        if self.applies_when:
            line += f" Applies when: {self.applies_when}"
        return line


@dataclass(frozen=True)
class ParseIssue:
    """Text the parser kept but that breaks the rule format; `jdad lint-kb` fails on it."""

    line: int
    kind: str
    message: str
    text: str = ""


@dataclass(frozen=True)
class Section:
    heading: str
    level: int
    tags: tuple[str, ...]
    body: str
    line: int = 0
    rules: tuple[Rule, ...] = ()
    issues: tuple[ParseIssue, ...] = ()

    @property
    def bullets(self) -> list[str]:
        return extract_bullets(self.body)


def _finish_rule(raw: str, applies: str | None, tags: tuple[str, ...], line: int, last_line: int = 0) -> Rule:
    text = " ".join(raw.split())
    rule_id = None
    match = _RULE_ID_SUFFIX_RE.search(text)
    if match:
        rule_id = match.group(1).strip()
        text = text[: match.start()]
    citation = None
    match = _CITATION_SUFFIX_RE.search(text)
    if match:
        citation = " ".join(match.group(1).split())
        text = text[: match.start()]
    return Rule(
        id=rule_id,
        text=text.strip(),
        citation=citation,
        applies_when=" ".join(applies.split()) if applies else None,
        tags=tags,
        line=line,
        last_line=max(last_line, line),
    )


def parse_rules(
    lines: list[tuple[int, str]], tags: tuple[str, ...]
) -> tuple[tuple[Rule, ...], tuple[ParseIssue, ...]]:
    """Parse a section body (numbered lines) into rules.

    Nothing is dropped silently: nested bullets and numbered items are kept
    (joined to the rule, or as a rule of their own) and reported as issues,
    and prose that isn't part of a rule is reported too.
    """
    rules: list[Rule] = []
    issues: list[ParseIssue] = []
    current: dict | None = None

    def close() -> None:
        nonlocal current
        if current is not None:
            rules.append(_finish_rule(current["raw"], current["applies"], tags, current["line"], current["last"]))
            current = None

    for number, line in lines:
        if not line.strip():
            close()
            continue
        start = _RULE_START_RE.match(line)
        numbered = _NUMBERED_RE.match(line) if not start else None
        if start or (numbered and not line[:1].isspace()):
            close()
            if numbered:
                issues.append(ParseIssue(number, "numbered", "numbered item: use a '- ' bullet", line))
            current = {"raw": (start or numbered).group(1), "applies": None, "line": number, "last": number}
            continue
        if line[:1].isspace():
            applies = _APPLIES_RE.match(line)
            nested = _NESTED_BULLET_RE.match(line) or _NUMBERED_RE.match(line)
            if current is None:
                issues.append(ParseIssue(number, "stray-text", "indented text that belongs to no rule", line))
                continue
            current["last"] = number
            if applies:
                current["applies"] = applies.group(1)
            elif nested:
                issues.append(
                    ParseIssue(number, "nested", "nested list item: make it a rule of its own", line)
                )
                current["raw"] += "; " + nested.group(1)
            else:
                current["raw"] += " " + line.strip()
            continue
        close()
        issues.append(ParseIssue(number, "stray-text", "text in a section that isn't a '- ' rule", line))
    close()
    return tuple(rules), tuple(issues)


@dataclass(frozen=True)
class PracticeDoc:
    topic: str
    relpath: str
    title: str
    preamble: str
    sections: tuple[Section, ...]
    text: str
    issues: tuple[ParseIssue, ...] = field(default=())

    @property
    def rules(self) -> list[Rule]:
        return [rule for section in self.sections for rule in section.rules]

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

    preamble_issues: list[ParseIssue] = []

    def close() -> None:
        nonlocal current
        if current is not None:
            tags = tuple(current["tags"])
            rules, issues = parse_rules(current["numbered"], tags)
            sections.append(
                Section(
                    heading=current["heading"],
                    level=current["level"],
                    tags=tags,
                    body="\n".join(current["body"]).strip("\n"),
                    line=current["line"],
                    rules=rules,
                    issues=issues,
                )
            )
            current = None

    for number, raw in enumerate(text.split("\n"), start=1):
        raw = raw.removesuffix("\r")
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
                    "numbered": [],
                    "line": number,
                }
                continue
        if current is None:
            preamble_lines.append(raw)
            if _RULE_START_RE.match(raw) or _NUMBERED_RE.match(raw):
                preamble_issues.append(
                    ParseIssue(number, "outside-section", "a rule before the first tagged section", raw)
                )
        else:
            current["body"].append(raw)
            current["numbered"].append((number, raw))

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
        issues=tuple(preamble_issues),
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
        """Every practice file that parses. A file that can't be read or parsed
        is logged and skipped, so one bad file doesn't break every listing
        tool; `jdad-mcp --check` and `jdad lint-kb` still fail on it."""
        docs: list[PracticeDoc] = []
        for path in self.practice_paths():
            try:
                docs.append(parse_practice(path, root=self.root))
            except (OSError, UnicodeDecodeError, ValueError) as exc:
                logger.warning("skipping practice %s: %s: %s", path.name, type(exc).__name__, exc)
        return docs

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
                            "rules": [],
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
                            "rules": [rule.as_dict() for rule in section.rules],
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
                if section.rules:
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
                for rule in section.rules:
                    lines.append(rule.checklist_line())
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

        # Only <stem>.md: the same set of files list_* returns and `jdad lint-kb` checks.
        resolved = (directory / f"{stem}.md").resolve()
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
