"""review_against_kb (roadmap P3.4): the KB rules that apply to a change, a review
rubric and a findings format. Paths only: no file is read, and no model is called;
the calling agent does the review. Stdlib only.

Tag inference is a small table of path rules (lower-cased, `/`-separated). A `.ts`
or `.js` file counts as frontend or backend only under a directory that says which;
anything the table doesn't know adds no tag.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

from jdad.kb import KNOWN_TAGS, KnowledgeBase

FINDING_FIELDS = ("rule_id", "file", "evidence", "severity")
SEVERITIES = ("blocker", "major", "minor")
RELEVANT_LIMIT = 5

_FRONTEND_EXT = {".tsx", ".jsx", ".vue", ".svelte", ".css", ".scss", ".sass", ".less", ".html"}
_BACKEND_EXT = {".py", ".go", ".rb", ".java", ".kt", ".rs", ".php", ".cs", ".ex", ".exs"}
_SCRIPT_EXT = {".ts", ".js", ".mjs", ".cjs"}
_FRONTEND_DIRS = {"components", "pages", "app", "ui", "public", "frontend", "web"}
_BACKEND_DIRS = {"api", "server", "routes", "handlers", "backend", "services"}
_DB_DIRS = {"migrations", "alembic", "models", "db", "database"}
_INFRA_DIRS = {"deploy", "k8s", "kubernetes", "helm", "terraform", "infra", "ansible"}
_LOCKFILES = {
    "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "uv.lock", "poetry.lock",
    "pipfile.lock", "pyproject.toml", "go.mod", "go.sum", "cargo.toml", "cargo.lock", "gemfile", "gemfile.lock",
}  # fmt: skip
_TEST_NAME_RE = re.compile(r"^(test_.*|.*_test\.[a-z]+|.*\.(test|spec)\.[a-z]+)$")
_REQUIREMENTS_RE = re.compile(r"^requirements[\w.-]*\.txt$")
_COMPOSE_RE = re.compile(r"^(docker-)?compose[\w.-]*\.ya?ml$")


def _tags_for(path: str) -> list[str]:
    p = PurePosixPath(path.strip().replace("\\", "/").lower())
    name, suffix, dirs = p.name, p.suffix, set(p.parts[:-1])
    tags: list[str] = []
    if suffix in _FRONTEND_EXT or (suffix in _SCRIPT_EXT and dirs & _FRONTEND_DIRS and not dirs & _BACKEND_DIRS):
        tags.append("frontend")
    if suffix in _BACKEND_EXT or (suffix in _SCRIPT_EXT and dirs & _BACKEND_DIRS):
        tags.append("backend")
    if suffix == ".sql" or name == "schema.prisma" or dirs & _DB_DIRS:
        tags.append("db")
    if (
        name.startswith("dockerfile")
        or _COMPOSE_RE.match(name)
        or suffix in {".tf", ".tfvars"}
        or name == "procfile"
        or (name.startswith("nginx") and suffix == ".conf")
        or dirs & _INFRA_DIRS
    ):
        tags.append("infra")
    if "tests" in dirs or "test" in dirs or "__tests__" in dirs or _TEST_NAME_RE.match(name):
        tags.append("testing")
    if ".github" in dirs and "workflows" in dirs or name == ".gitlab-ci.yml" or ".circleci" in dirs:
        tags.append("ci")
    if name in _LOCKFILES or _REQUIREMENTS_RE.match(name):
        tags.append("supply-chain")
    return tags


def infer_tags(changed_files: list[str]) -> dict[str, list[str]]:
    """{tag: [files]} for the files whose paths say which KB tags apply, in input order."""
    inferred: dict[str, list[str]] = {}
    for path in changed_files:
        for tag in _tags_for(path):
            inferred.setdefault(tag, []).append(path)
    return inferred


RUBRIC = [
    "Correctness first: does the change do what the summary says, without breaking callers, data or security? A wrong result outranks every rule below.",
    "Then the KB rules in the checklist that apply to this diff. Cite each by its rule ID; skip a rule whose 'Applies when' note doesn't fit.",
    "Skip style: no naming, formatting or taste comments unless a cited rule requires it.",
    "Every finding needs evidence from the diff: the file and the line or code it is about. No evidence, no finding.",
    "No findings is a valid result. Say so rather than padding the list.",
]

FINDINGS_FORMAT = {
    "fields": list(FINDING_FIELDS),
    "severity": list(SEVERITIES),
    "example": "- rule: perf.db.n-plus-one | file: api/orders.py:42 | evidence: one query per order inside the loop | severity: major",
    "note": "Use rule_id `correctness` for a correctness problem no KB rule covers.",
}


def build_review(
    kb: KnowledgeBase, changed_files: list[str], summary: str, tags: list[str] | None = None
) -> dict[str, Any]:
    files = [f for f in changed_files if f and f.strip()]
    inferred = infer_tags(files)
    passed = [t.strip().lower() for t in (tags or []) if t and t.strip()]
    unknown = [t for t in passed if t not in KNOWN_TAGS]
    if unknown:
        raise ValueError(f"unknown tag(s) {', '.join(repr(t) for t in unknown)}: use {', '.join(KNOWN_TAGS)}")
    wanted = sorted(set(inferred) | set(passed))
    review: dict[str, Any] = {
        "summary": summary.strip(),
        "changed_files": files,
        "tags": wanted,
        "inferred_from": inferred,
        "checklist": "",
        "relevant": [],
        "rubric": RUBRIC,
        "findings_format": FINDINGS_FORMAT,
        "kb_version": kb.version()["display"],
        "note": None,
    }
    if not wanted:
        review["note"] = (
            "No KB tags could be inferred from these paths. Pass tags (one or more of "
            + ", ".join(KNOWN_TAGS)
            + ") to get the matching rules; this review returns none rather than the whole KB."
        )
        return review
    review["checklist"] = kb.get_checklist(wanted, phase="review")
    if summary.strip():
        hits = kb.search_practices(summary, tags=wanted, limit=RELEVANT_LIMIT)
        review["relevant"] = [{"id": h["id"], "heading": h.get("heading"), "snippet": h.get("snippet")} for h in hits]
    return review
