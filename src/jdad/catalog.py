"""Validate the canonical skills catalog (roadmap P1.4, ADR 0001). Stdlib only.

``catalog/skills/<name>/SKILL.md`` must follow the Agent Skills spec:
spec-only frontmatter keys, ``name`` equal to the directory (lowercase,
digits and single hyphens, at most 64 characters), a 1-1024 character
``description``, ``compatibility`` of at most 500 characters, a mapping for
``metadata``, and a body under 500 lines. ``catalog/rules/<name>.md`` takes
``description`` (required), ``globs`` and ``alwaysApply``.

The frontmatter reader handles the YAML these files use (scalars, quoted
strings, nested mappings by indentation, block and inline lists). Anything
else is a finding, not a guess. The reference validator (``agentskills
validate`` from skills-ref) runs alongside it in ./verify.

Usage: ``python -m jdad.catalog validate [ROOT]``
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

SKILL_KEYS = ("name", "description", "license", "compatibility", "metadata", "allowed-tools")
RULE_KEYS = ("description", "globs", "alwaysApply")
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_NAME = 64
MAX_DESCRIPTION = 1024
MAX_COMPATIBILITY = 500
MAX_BODY_LINES = 500


@dataclass(frozen=True)
class Finding:
    path: str
    message: str

    def format(self) -> str:
        return f"{self.path}: {self.message}"


class FrontmatterError(ValueError):
    pass


def split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter text, body). The file must start with '---'."""
    lines = text.split("\n")
    if not lines or lines[0].rstrip("\r") != "---":
        raise FrontmatterError("no frontmatter: the file must start with a '---' line")
    for index, line in enumerate(lines[1:], start=1):
        if line.rstrip("\r") == "---":
            return "\n".join(lines[1:index]), "\n".join(lines[index + 1:])
    raise FrontmatterError("frontmatter is never closed with a '---' line")


def _scalar(raw: str) -> object:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [_scalar(part) for part in inner.split(",")] if inner else []
    if value in ("true", "false"):
        return value == "true"
    if value[:1] in "{&*!|>%@`":
        raise FrontmatterError(f"unsupported YAML value: {value[:40]!r}")
    return value


def parse_frontmatter(text: str) -> dict:
    """A YAML subset: `key: value`, nested mappings by indentation, `- item` lists."""
    root: dict = {}
    # Stack of (indent, container) for mappings; lists attach to their key.
    stack: list[tuple[int, dict]] = [(-1, root)]
    pending_key: tuple[dict, str, int] | None = None
    for number, raw in enumerate(text.split("\n"), start=2):
        line = raw.rstrip("\r")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if "\t" in line[: len(line) - len(line.lstrip())]:
            raise FrontmatterError(f"line {number}: tabs in indentation")
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if stripped.startswith("- "):
            if pending_key is None or indent <= pending_key[2]:
                raise FrontmatterError(f"line {number}: a list item with no key above it")
            parent, key, _ = pending_key
            if not isinstance(parent.get(key), list):
                if parent.get(key) not in (None, {}):
                    raise FrontmatterError(f"line {number}: '{key}' mixes a value and a list")
                parent[key] = []
            parent[key].append(_scalar(stripped[2:]))
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+):(?:\s+(.*))?", stripped)
        if not match:
            raise FrontmatterError(f"line {number}: not a 'key: value' line: {stripped[:60]!r}")
        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            raise FrontmatterError(f"line {number}: bad indentation")
        container = stack[-1][1]
        key, value = match.group(1), match.group(2)
        if key in container:
            raise FrontmatterError(f"line {number}: duplicate key '{key}'")
        if value is None or value.strip() == "":
            container[key] = {}
            stack.append((indent, container[key]))
            pending_key = (container, key, indent)
        else:
            container[key] = _scalar(value)
            pending_key = None
    return root


def _read(path: Path, root: Path) -> tuple[dict, str] | Finding:
    rel = path.relative_to(root).as_posix()
    try:
        meta_text, body = split_frontmatter(path.read_text(encoding="utf-8"))
        return parse_frontmatter(meta_text), body
    except (OSError, UnicodeDecodeError) as exc:
        return Finding(rel, f"unreadable: {exc}")
    except FrontmatterError as exc:
        return Finding(rel, str(exc))


def validate_skill(path: Path, root: Path) -> list[Finding]:
    rel = path.relative_to(root).as_posix()
    read = _read(path, root)
    if isinstance(read, Finding):
        return [read]
    meta, body = read
    findings: list[Finding] = []

    def bad(message: str) -> None:
        findings.append(Finding(rel, message))

    for key in sorted(set(meta) - set(SKILL_KEYS)):
        bad(f"unknown frontmatter key '{key}' (allowed: {', '.join(SKILL_KEYS)}; tool extras go under metadata)")
    name = meta.get("name")
    directory = path.parent.name
    if not isinstance(name, str) or not name:
        bad("'name' is required")
    else:
        if len(name) > MAX_NAME:
            bad(f"'name' is {len(name)} characters (at most {MAX_NAME})")
        if not NAME_RE.match(name):
            bad(f"'name' {name!r} must be lowercase letters, digits and single hyphens")
        if name != directory:
            bad(f"'name' {name!r} must equal its directory name {directory!r}")
    description = meta.get("description")
    if not isinstance(description, str) or not description.strip():
        bad("'description' is required")
    elif len(description) > MAX_DESCRIPTION:
        bad(f"'description' is {len(description)} characters (at most {MAX_DESCRIPTION})")
    compatibility = meta.get("compatibility")
    if compatibility is not None and (not isinstance(compatibility, str) or len(compatibility) > MAX_COMPATIBILITY):
        bad(f"'compatibility' must be text of at most {MAX_COMPATIBILITY} characters")
    if "metadata" in meta and not isinstance(meta["metadata"], dict):
        bad("'metadata' must be a mapping")
    for key in ("license", "allowed-tools"):
        if key in meta and not isinstance(meta[key], str):
            bad(f"'{key}' must be text")
    body_lines = len(body.rstrip("\n").split("\n")) if body.strip() else 0
    if body_lines >= MAX_BODY_LINES:
        bad(f"body is {body_lines} lines (keep it under {MAX_BODY_LINES}; move detail into referenced files)")
    return findings


def validate_rule(path: Path, root: Path) -> list[Finding]:
    rel = path.relative_to(root).as_posix()
    read = _read(path, root)
    if isinstance(read, Finding):
        return [read]
    meta, _body = read
    findings = [Finding(rel, f"unknown frontmatter key '{k}' (allowed: {', '.join(RULE_KEYS)})") for k in sorted(set(meta) - set(RULE_KEYS))]
    if not isinstance(meta.get("description"), str) or not meta["description"].strip():
        findings.append(Finding(rel, "'description' is required"))
    globs = meta.get("globs")
    if globs is not None and not (isinstance(globs, str) or (isinstance(globs, list) and all(isinstance(g, str) for g in globs))):
        findings.append(Finding(rel, "'globs' must be a string or a list of strings"))
    if "alwaysApply" in meta and not isinstance(meta["alwaysApply"], bool):
        findings.append(Finding(rel, "'alwaysApply' must be true or false"))
    return findings


def validate_catalog(root: Path) -> list[Finding]:
    root = root.resolve()
    catalog = root / "catalog"
    findings: list[Finding] = []
    skills = catalog / "skills"
    if skills.is_dir():
        for directory in sorted(p for p in skills.iterdir() if p.is_dir()):
            skill = directory / "SKILL.md"
            if not skill.is_file():
                findings.append(Finding(directory.relative_to(root).as_posix(), "missing SKILL.md"))
                continue
            findings.extend(validate_skill(skill, root))
        for stray in sorted(p for p in skills.iterdir() if p.is_file()):
            findings.append(Finding(stray.relative_to(root).as_posix(), "skills are directories: catalog/skills/<name>/SKILL.md"))
    rules = catalog / "rules"
    if rules.is_dir():
        for rule in sorted(rules.glob("*.md")):
            if rule.name != "README.md":
                findings.extend(validate_rule(rule, root))
    return findings


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] != "validate" or len(args) > 2:
        print("usage: python -m jdad.catalog validate [ROOT]", file=sys.stderr)
        return 2
    root = Path(args[1]) if len(args) == 2 else Path.cwd()
    findings = validate_catalog(root)
    for finding in findings:
        print(finding.format())
    if findings:
        print(f"catalog: {len(findings)} finding(s)", file=sys.stderr)
        return 1
    print(f"catalog: ok ({root.resolve()})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
