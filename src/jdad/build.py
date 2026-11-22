"""Compile the catalog into each tool's files (roadmap P1.5, ADR 0001).

Targets, all generated (never edit them by hand):

- ``skills/<name>/``: Claude Code plugin skills (Grok Build reads them too).
  Keys under ``metadata.claude`` become top-level frontmatter, Claude's
  extension point (e.g. ``disable-model-invocation``).
- ``generated/agents-skills/<name>/``: Agent Skills for ``.agents/skills/``
  (Codex, Cursor). Tool-specific ``metadata.<tool>`` keys are dropped.
- ``generated/cursor-rules/<name>.mdc``: Cursor rules from ``catalog/rules/``
  (``description``, ``globs``, ``alwaysApply``).

(Not under dist/: `uv build` writes a dist/.gitignore that ignores everything
there, and these outputs are committed so `build --check` can hold them.)

Each generated file carries a header naming its source: ``metadata.generated``
in skill frontmatter (frontmatter must come first, and an HTML comment would
be read by agents), a first body line in ``.mdc`` files. Other files in a
skill directory are copied as they are. ``build --check`` compares without
writing and lists every stale, missing or extra file. Stdlib only.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from jdad.catalog import parse_frontmatter, split_frontmatter, validate_catalog

TOOL_KEYS = ("claude", "codex", "cursor", "grok")
CLAUDE_DIR = Path("skills")
AGENTS_DIR = Path("generated") / "agents-skills"
CURSOR_DIR = Path("generated") / "cursor-rules"
OUTPUT_ROOTS = (CLAUDE_DIR, AGENTS_DIR, CURSOR_DIR)
_PLAIN_RE = re.compile(r"^[A-Za-z0-9_./()'+@,][^\n]*$")


class BuildError(Exception):
    pass


# ---- a small YAML emitter for the frontmatter subset the catalog uses -------


def _scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    plain = (
        _PLAIN_RE.match(text)
        and ": " not in text
        and " #" not in text
        and not text.endswith(":")
        and text.strip() == text
        and text not in ("true", "false", "null", "~", "yes", "no")
    )
    return text if plain else json.dumps(text, ensure_ascii=False)


def dump_frontmatter(meta: dict, indent: int = 0) -> str:
    lines: list[str] = []
    pad = " " * indent
    for key, value in meta.items():
        if isinstance(value, dict):
            lines.append(f"{pad}{key}:")
            lines.append(dump_frontmatter(value, indent + 2))
        elif isinstance(value, list):
            lines.append(f"{pad}{key}:")
            lines.extend(f"{pad}  - {_scalar(item)}" for item in value)
        else:
            lines.append(f"{pad}{key}: {_scalar(value)}")
    return "\n".join(line for line in lines if line)


# ---- targets ---------------------------------------------------------------


def _header(source: str) -> str:
    return f"jdad build from {source}; do not edit"


def _skill_file(meta: dict, body: str, source: str, target: str) -> str:
    out = {k: v for k, v in meta.items() if k != "metadata"}
    metadata = dict(meta.get("metadata") or {})
    extras = metadata.pop("claude", None) if target == "claude" else None
    for tool in TOOL_KEYS:
        metadata.pop(tool, None)
    if isinstance(extras, dict):
        for key, value in extras.items():
            if key in out:
                raise BuildError(f"{source}: metadata.claude.{key} collides with a top-level key")
            out[key] = value
    metadata["generated"] = _header(source)
    out["metadata"] = metadata
    return f"---\n{dump_frontmatter(out)}\n---\n{body}"


def _rule_file(meta: dict, body: str, source: str) -> str:
    out = {"description": meta["description"]}
    if "globs" in meta:
        globs = meta["globs"]
        out["globs"] = ",".join(globs) if isinstance(globs, list) else globs
    out["alwaysApply"] = bool(meta.get("alwaysApply", False))
    return f"---\n{dump_frontmatter(out)}\n---\n> {_header(source)}\n\n{body.lstrip(chr(10))}"


def _no_symlinks(root: Path, rel: Path) -> None:
    """Refuse a path with any symlinked component below the repo root, so
    the build never reads from or writes through a link."""
    current = root
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            raise BuildError(f"{current.relative_to(root).as_posix()} is a symlink; the catalog and its outputs must be real files")


@dataclass(frozen=True)
class Output:
    path: Path  # relative to the repo root
    data: bytes


def plan(root: Path) -> list[Output]:
    """Every file the build should produce, in memory."""
    findings = validate_catalog(root)
    if findings:
        raise BuildError("catalog is invalid:\n" + "\n".join(f.format() for f in findings))
    outputs: list[Output] = []
    skills = root / "catalog" / "skills"
    for base in (Path("catalog"), Path("catalog/skills"), Path("catalog/rules")):
        if (root / base).exists():
            _no_symlinks(root, base)
    for directory in sorted(p for p in skills.iterdir() if p.is_dir() or p.is_symlink()) if skills.is_dir() else []:
        _no_symlinks(root, directory.relative_to(root))
        for item in directory.rglob("*"):
            if item.is_symlink():
                raise BuildError(f"{item.relative_to(root).as_posix()} is a symlink; the catalog and its outputs must be real files")
        source = f"catalog/skills/{directory.name}/SKILL.md"
        meta_text, body = split_frontmatter((directory / "SKILL.md").read_text(encoding="utf-8"))
        meta = parse_frontmatter(meta_text)
        for target, base in (("claude", CLAUDE_DIR), ("agents", AGENTS_DIR)):
            outputs.append(Output(base / directory.name / "SKILL.md", _skill_file(meta, body, source, target).encode()))
            for extra in sorted(p for p in directory.rglob("*") if p.is_file() and p.name != "SKILL.md"):
                outputs.append(Output(base / directory.name / extra.relative_to(directory), extra.read_bytes()))
    rules = root / "catalog" / "rules"
    for rule in sorted(rules.glob("*.md")) if rules.is_dir() else []:
        if rule.name == "README.md":
            continue
        _no_symlinks(root, rule.relative_to(root))
        meta_text, body = split_frontmatter(rule.read_text(encoding="utf-8"))
        outputs.append(
            Output(CURSOR_DIR / f"{rule.stem}.mdc", _rule_file(parse_frontmatter(meta_text), body, f"catalog/rules/{rule.name}").encode())
        )
    return outputs


def _existing(root: Path) -> set[Path]:
    found: set[Path] = set()
    for base in OUTPUT_ROOTS:
        if (root / base).exists() or (root / base).is_symlink():
            _no_symlinks(root, base)
        directory = root / base
        if directory.is_dir():
            for p in directory.rglob("*"):
                if p.is_symlink():
                    raise BuildError(f"{p.relative_to(root).as_posix()} is a symlink; the catalog and its outputs must be real files")
                if p.is_file() and p.name != ".DS_Store":
                    found.add(p.relative_to(root))
    return found


def check(root: Path) -> list[str]:
    """Problems that `jdad build` would fix; empty when everything is current."""
    root = root.resolve()
    outputs = plan(root)
    existing = _existing(root)  # raises on a symlinked output path
    problems = []
    for output in outputs:
        path = root / output.path
        if not path.is_file():
            problems.append(f"missing: {output.path.as_posix()}")
        elif path.read_bytes() != output.data:
            problems.append(f"stale: {output.path.as_posix()}")
    expected = {o.path for o in outputs}
    for extra in sorted(existing - expected):
        problems.append(f"not generated from the catalog: {extra.as_posix()}")
    return problems


def build(root: Path) -> list[str]:
    """Write every output and delete files the catalog no longer produces."""
    root = root.resolve()
    outputs = plan(root)
    expected = {o.path for o in outputs}
    changed = []
    for extra in sorted(_existing(root) - expected):
        (root / extra).unlink()
        changed.append(f"removed {extra.as_posix()}")
    for output in outputs:
        path = root / output.path
        _no_symlinks(root, output.path)
        if not path.is_file() or path.read_bytes() != output.data:
            path.parent.mkdir(parents=True, exist_ok=True)
            _no_symlinks(root, output.path.parent)
            # Write a temp file beside it and rename over: a rename never
            # follows a link at the destination.
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".jdad-build-")
            with os.fdopen(fd, "wb") as handle:
                handle.write(output.data)
            os.chmod(tmp, 0o644)  # mkstemp makes 0600
            os.replace(tmp, path)
            changed.append(f"wrote {output.path.as_posix()}")
    for base in OUTPUT_ROOTS:  # drop directories emptied above
        directory = root / base
        if directory.is_dir():
            for sub in sorted((p for p in directory.rglob("*") if p.is_dir()), reverse=True):
                if not any(sub.iterdir()):
                    shutil.rmtree(sub)
    return changed
