"""review_against_kb (roadmap P3.4, JON-1367): rules inferred from the changed files,
a rubric and a findings format. The server does no model calls; the agent reviews."""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

import pytest
from mcp import Client

from jdad.kb import KNOWN_TAGS, KnowledgeBase
from jdad.review import (
    FINDING_FIELDS,
    SEVERITIES,
    UnknownTagError,
    build_review,
    infer_tags,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "review"
ITEM_ID_RE = re.compile(r"^- \[ \] (\S+): ", re.MULTILINE)
SEEDED = {
    "frontend": "rev.frontend.lazy",
    "backend": "rev.backend.timeouts",
    "db": "rev.db.index",
    "infra": "rev.infra.limits",
    "testing": "rev.testing.failures",
    "ci": "rev.ci.required",
    "supply-chain": "rev.supply.lockfile",
}

# ---- tag inference from paths ----

FILE_SETS = {
    "frontend": ["web/src/components/Button.tsx", "web/styles/site.scss", "app/pages/index.vue", "src/ui/menu.js"],
    "backend": ["api/handlers.py", "cmd/server/main.go", "src/server/routes/users.ts", "lib/billing.rb"],
    "db": ["migrations/0004_add_index.sql", "alembic/versions/3f2_users.py", "prisma/schema.prisma", "db/queries.sql"],
    "infra": ["Dockerfile", "deploy/docker-compose.yml", "infra/main.tf", "k8s/deployment.yaml"],
}


@pytest.mark.parametrize("tag", sorted(FILE_SETS))
def test_each_file_set_infers_its_tag(tag: str) -> None:
    inferred = infer_tags(FILE_SETS[tag])
    assert tag in inferred
    assert sorted(inferred[tag]) == sorted(f for f in FILE_SETS[tag] if f in inferred[tag])
    # every file in the set is explained by its tag (the alembic .py also counts as backend)
    assert set(FILE_SETS[tag]) == set(inferred[tag])


@pytest.mark.parametrize(
    ("path", "tags"),
    [
        ("web/src/components/Button.tsx", {"frontend"}),
        ("README.md", set()),
        ("docs/notes.txt", set()),
        ("src/server/routes/users.ts", {"backend"}),
        ("src/lib/format.ts", set()),  # a .ts outside the known dirs is not guessed
        ("app/api/users/route.ts", {"backend"}),  # a backend dir wins over a frontend one
        ("tests/test_api.py", {"backend", "testing"}),
        ("web/Button.test.tsx", {"frontend", "testing"}),
        (".github/workflows/ci.yml", {"ci"}),
        ("uv.lock", {"supply-chain"}),
        ("frontend/package.json", {"supply-chain"}),
        ("requirements-dev.txt", {"supply-chain"}),
        ("DOCKERFILE.prod", {"infra"}),
        ("Migrations/0001.SQL", {"db"}),
        ("deploy/update.sh", {"infra"}),
        # Checker on #38 (JON-1393 item 10): CI, compose, Terraform, test dirs, .css, models/
        (".gitlab-ci.yml", {"ci"}),
        (".circleci/config.yml", {"ci"}),
        (".github/ISSUE_TEMPLATE/bug.md", set()),  # .github/ alone is not CI
        ("ci/workflows/build.yml", set()),  # workflows/ alone is not CI
        ("compose.yaml", {"infra"}),
        ("docker-compose.prod.yml", {"infra"}),
        ("main.tf", {"infra"}),
        ("prod.tfvars", {"infra"}),
        ("terraform/variables.json", {"infra"}),
        ("nginx.conf", {"infra"}),
        ("Procfile", {"infra"}),
        ("tests/fixtures/data.json", {"testing"}),
        ("test/helpers.rb", {"backend", "testing"}),
        ("src/__tests__/Button.jsx", {"frontend", "testing"}),
        ("pkg/handler_test.go", {"backend", "testing"}),
        ("web/app.spec.ts", {"frontend", "testing"}),
        ("styles/site.css", {"frontend"}),
        ("app/models/user.rb", {"backend", "db"}),
        ("prisma/schema.prisma", {"db"}),
    ],
)
def test_path_rules(path: str, tags: set[str]) -> None:
    assert set(infer_tags([path])) == tags


# Every entry of the path-rule tables, written out (Checker on #38, JON-1393 item 13: the
# mutation pass's survivors were mostly table entries no test named). A path for each
# entry must infer its tag, and the tables must hold exactly these entries, so an entry
# added to review.py without a line here fails.
TABLE_SPEC = {
    "_FRONTEND_EXT": (["frontend"], "src/file{}", [".tsx", ".jsx", ".vue", ".svelte", ".css", ".scss", ".sass", ".less", ".html"]),
    "_BACKEND_EXT": (["backend"], "src/file{}", [".py", ".go", ".rb", ".java", ".kt", ".rs", ".php", ".cs", ".ex", ".exs"]),
    "_FRONTEND_DIRS": (["frontend"], "{}/file.ts", ["components", "pages", "app", "ui", "public", "frontend", "web"]),
    "_BACKEND_DIRS": (["backend"], "{}/file.ts", ["api", "server", "routes", "handlers", "backend", "services"]),
    "_DB_DIRS": (["db"], "{}/file.txt", ["migrations", "alembic", "models", "db", "database"]),
    "_INFRA_DIRS": (["infra"], "{}/file.txt", ["deploy", "k8s", "kubernetes", "helm", "terraform", "infra", "ansible"]),
    "_LOCKFILES": (
        ["supply-chain"],
        "{}",
        ["package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "uv.lock", "poetry.lock", "Pipfile.lock",
         "pyproject.toml", "go.mod", "go.sum", "Cargo.toml", "Cargo.lock", "Gemfile", "Gemfile.lock"],
    ),
}  # fmt: skip
TABLE_CASES = [(table, template.format(entry), tags) for table, (tags, template, entries) in TABLE_SPEC.items() for entry in entries]
# A .ts/.js/.mjs/.cjs file is frontend under a frontend dir and backend under a backend dir.
SCRIPT_EXT = [".ts", ".js", ".mjs", ".cjs"]
TABLE_CASES += [("_SCRIPT_EXT", f"components/file{ext}", ["frontend"]) for ext in SCRIPT_EXT]
TABLE_CASES += [("_SCRIPT_EXT", f"api/file{ext}", ["backend"]) for ext in SCRIPT_EXT]


@pytest.mark.parametrize(("table", "path", "tags"), TABLE_CASES, ids=[c[1] for c in TABLE_CASES])
def test_every_table_entry_infers_its_tag(table: str, path: str, tags: list[str]) -> None:
    assert sorted(infer_tags([path])) == tags


def test_the_tables_hold_exactly_the_tested_entries() -> None:
    from jdad import review

    for table, (_tags, _template, entries) in TABLE_SPEC.items():
        assert getattr(review, table) == {e.lower() for e in entries}, table
    assert review._SCRIPT_EXT == set(SCRIPT_EXT)


@pytest.mark.parametrize(
    ("path", "tags"),
    [
        ("  api/x.py ", {"backend"}),  # surrounding spaces are stripped
        ("deploy\\run.sh", {"infra"}),  # Windows separators count as /
        ("notes/models", set()),  # a file named like a directory is not that directory
        ("docs/nginx-notes.md", set()),  # nginx*.conf only
        ("test_api.py", {"backend", "testing"}),  # test_ name outside a tests/ dir
        ("requirements.txt.bak", set()),  # requirements*.txt, nothing after
    ],
)
def test_path_normalisation_and_name_rules(path: str, tags: set[str]) -> None:
    assert set(infer_tags([path])) == tags


def test_inference_keeps_each_tags_files_in_input_order() -> None:
    files = ["b.sql", "x.md", "a.sql", "api/x.py"]
    assert infer_tags(files) == {"db": ["b.sql", "a.sql"], "backend": ["api/x.py"]}


def test_inferred_tags_are_known_tags() -> None:
    every = [f for files in FILE_SETS.values() for f in files] + [".github/workflows/x.yml", "uv.lock", "tests/test_x.py"]
    assert set(infer_tags(every)) <= set(KNOWN_TAGS)


# ---- the review bundle ----


@pytest.mark.parametrize("tag", sorted(FILE_SETS))
def test_output_holds_only_rules_whose_tags_match(tag: str) -> None:
    review = build_review(KnowledgeBase(FIXTURE), FILE_SETS[tag], "a change")
    ids = set(ITEM_ID_RE.findall(review["checklist"]))
    assert SEEDED[tag] in ids
    others = set(SEEDED.values()) - {SEEDED[t] for t in review["tags"]}
    assert not ids & others, ids & others


def test_repo_kb_review_rules_all_carry_a_matching_tag() -> None:
    kb = KnowledgeBase(REPO_ROOT)
    tags_of = {r.id: {t.lower() for t in s.tags} for d in kb.practices() for s in d.sections for r in s.rules}
    review = build_review(kb, ["migrations/0004_add_index.sql"], "add an index for the orders filter")
    assert review["tags"] == ["db"]
    ids = ITEM_ID_RE.findall(review["checklist"]) + [hit["id"] for hit in review["relevant"]]
    assert ids and all("db" in tags_of[i] for i in ids), [i for i in ids if "db" not in tags_of[i]]


def test_the_checklist_is_the_review_phase() -> None:
    review = build_review(KnowledgeBase(FIXTURE), ["api/x.py"], "errors")
    ids = ITEM_ID_RE.findall(review["checklist"])
    assert "rev.backend.errors" in ids and "rev.backend.version" not in ids
    assert "Phase: review" in review["checklist"].splitlines()


def test_passed_tags_are_added_to_inferred_ones() -> None:
    review = build_review(KnowledgeBase(FIXTURE), ["api/x.py"], "x", tags=["DB", " ci "])
    assert review["tags"] == ["backend", "ci", "db"]
    assert review["inferred_from"] == {"backend": ["api/x.py"]}


def test_blank_files_and_tags_are_dropped() -> None:
    review = build_review(KnowledgeBase(FIXTURE), ["", "  ", "api/x.py"], "x", tags=["", " ", "ci"])
    assert review["changed_files"] == ["api/x.py"]
    assert review["tags"] == ["backend", "ci"]


def test_an_unknown_tag_is_an_error_that_names_it() -> None:
    with pytest.raises(UnknownTagError, match="'frontnd'"):
        build_review(KnowledgeBase(FIXTURE), ["api/x.py"], "x", tags=["frontnd"])


def test_unknown_tag_error_is_a_value_error() -> None:
    """Callers outside the server catch ValueError (Checker on #39, mutant I9j; JON-1393 item 16)."""
    assert issubclass(UnknownTagError, ValueError)


def test_no_tags_means_no_rules_and_a_note() -> None:
    review = build_review(KnowledgeBase(FIXTURE), ["README.md"], "docs only")
    assert review["tags"] == [] and review["checklist"] == "" and review["relevant"] == []
    assert "tags" in review["note"]
    assert all(tag in review["note"] for tag in KNOWN_TAGS), review["note"]


def test_a_blank_summary_gets_no_relevant_hits() -> None:
    review = build_review(KnowledgeBase(FIXTURE), ["api/x.py"], "   ")
    assert review["summary"] == "" and review["relevant"] == []
    assert "rev.backend.timeouts" in review["checklist"]


def test_every_unknown_tag_is_named_and_known_ones_are_not() -> None:
    """Checker on #39, mutant H54 (JON-1393 item 18): not just the first."""
    with pytest.raises(UnknownTagError) as excinfo:
        build_review(KnowledgeBase(FIXTURE), ["api/x.py"], "x", tags=["frontnd", "ci", "bakend"])
    named = str(excinfo.value).split(":", 1)[0]
    assert named == "unknown tag(s) 'frontnd', 'bakend'"


@pytest.mark.parametrize(
    ("files", "tags"),
    [(["api/x.py"], None), (["README.md"], ["ci"])],
    ids=["inferred", "passed"],
)
def test_the_note_is_none_when_there_are_tags(files: list[str], tags: list[str] | None) -> None:
    """Checker on #39, mutant H29 (JON-1393 item 18): None, not an empty string."""
    review = build_review(KnowledgeBase(FIXTURE), files, "x", tags=tags)
    assert review["tags"]
    assert review["note"] is None


def test_relevant_hits_carry_id_heading_and_snippet() -> None:
    review = build_review(KnowledgeBase(FIXTURE), ["api/x.py"], "timeout on outbound calls")
    hit = review["relevant"][0]
    assert set(hit) == {"id", "heading", "snippet"}
    assert hit["id"] == "rev.backend.timeouts" and hit["heading"] and "timeout" in hit["snippet"].lower()


def test_relevant_hits_come_from_the_summary_within_the_tags() -> None:
    review = build_review(KnowledgeBase(FIXTURE), ["api/x.py", "a.sql"], "timeout on outbound calls")
    assert review["relevant"][0]["id"] == "rev.backend.timeouts"
    assert len(review["relevant"]) <= 5
    assert {hit["id"] for hit in review["relevant"]} <= {"rev.backend.timeouts", "rev.backend.errors", "rev.backend.version", "rev.db.index"}


def test_relevant_hits_are_capped_at_five() -> None:
    """Nine short fixture rules all match; only five come back."""
    summary = "lazy images timeout outbound index columns memory limit failure path required check lockfile errors version"
    review = build_review(KnowledgeBase(FIXTURE), ["a.sql"], summary, tags=["frontend", "backend", "infra", "testing", "ci", "supply-chain"])
    assert len(KnowledgeBase(FIXTURE).search_practices(summary, tags=review["tags"], limit=50)) > 5
    assert len(review["relevant"]) == 5


def test_rubric_puts_correctness_first_and_skips_style() -> None:
    rubric = build_review(KnowledgeBase(FIXTURE), ["api/x.py"], "x")["rubric"]
    text = "\n".join(rubric).lower()
    assert "correctness" in rubric[0].lower()
    assert "skip style" in text
    assert "evidence" in text and "no findings" in text
    assert "applies when" in text and "rule id" in text


def test_findings_format_has_the_four_fields() -> None:
    fmt = build_review(KnowledgeBase(FIXTURE), ["api/x.py"], "x")["findings_format"]
    assert FINDING_FIELDS == ("rule_id", "file", "evidence", "severity")
    assert fmt["fields"] == list(FINDING_FIELDS)
    assert fmt["severity"] == list(SEVERITIES) == ["blocker", "major", "minor"]
    example = fmt["example"]
    assert all(f"{field}:" in example for field in ("rule", "file", "evidence", "severity"))
    assert "`correctness`" in fmt["note"]


def test_review_echoes_the_summary_and_pins_the_kb_version() -> None:
    review = build_review(KnowledgeBase(FIXTURE), ["api/x.py"], "  add retries  ")
    assert review["summary"] == "add retries"
    assert review["changed_files"] == ["api/x.py"]
    assert "kb_version" in review


def test_review_kb_version_is_the_sha_and_newest_entry_date(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Checker on #38 (JON-1393 item 11): the value, not just the key."""
    root = tmp_path / "kb"
    shutil.copytree(FIXTURE, root)
    (root / "sources" / "2026-03-04-retries.md").write_text("---\ntitle: x\n---\n")
    (root / "sources" / "2026-01-02-older.md").write_text("---\ntitle: x\n---\n")
    monkeypatch.setenv("JDAD_GIT_SHA", "0123abcdef")
    review = build_review(KnowledgeBase(root), ["api/x.py"], "add retries")
    assert review["kb_version"] == "0123abcdef (2026-03-04)"


# ---- the MCP tool, the prompt and /jdad review ----


@pytest.mark.anyio
async def test_the_tool_is_read_only_and_returns_the_bundle(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KB_ROOT", str(FIXTURE))
    tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    tool = tools["review_against_kb"]
    assert tool.annotations.read_only_hint is True and tool.annotations.open_world_hint is False
    assert set(tool.input_schema["required"]) == {"changed_files", "summary"}
    result = await client.call_tool("review_against_kb", {"changed_files": ["a.sql"], "summary": "index"})
    data = result.structured_content
    assert data["tags"] == ["db"] and "rev.db.index" in data["checklist"]
    result = await client.call_tool("review_against_kb", {"changed_files": ["a.sql"], "summary": "x", "tags": ["ci"]})
    assert result.structured_content["tags"] == ["ci", "db"]


@pytest.mark.anyio
async def test_an_unknown_tag_reaches_the_client_named_and_logs_no_traceback(
    client: Client, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Checker on #38 (JON-1393 item 9): the client saw only "Error executing tool
    review_against_kb" and the server logged a traceback."""
    monkeypatch.setenv("KB_ROOT", str(FIXTURE))
    with caplog.at_level(logging.INFO, logger="mcp.server.mcpserver.server"):
        result = await client.call_tool("review_against_kb", {"changed_files": ["a.sql"], "summary": "x", "tags": ["frontnd"]})
    assert result.is_error
    text = result.content[0].text
    assert "'frontnd'" in text and all(tag in text for tag in KNOWN_TAGS), text
    assert not [r for r in caplog.records if r.exc_info or r.levelno >= logging.ERROR]
    assert any("frontnd" in r.getMessage() for r in caplog.records)


@pytest.mark.anyio
async def test_only_an_unknown_tag_is_passed_through_other_errors_stay_generic(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Any other failure is still a crash: its text stays on the server."""
    from jdad import server

    def boom(*_args: object, **_kwargs: object) -> None:
        raise ValueError("internal detail")

    monkeypatch.setattr(server, "build_review", boom)
    result = await client.call_tool("review_against_kb", {"changed_files": ["a.sql"], "summary": "x"})
    assert result.is_error
    assert result.content[0].text == "Error executing tool review_against_kb"


@pytest.mark.anyio
async def test_the_prompt_names_the_tool_and_the_format(client: Client) -> None:
    prompts = {p.name for p in (await client.list_prompts()).prompts}
    assert "review-against-kb" in prompts
    from jdad import server

    text = server.review_against_kb_prompt(changed_files="api/x.py, a.sql", summary="add retries")
    assert "review_against_kb" in text and "api/x.py" in text and "add retries" in text
    assert all(field in text for field in FINDING_FIELDS)
    assert "skip style" in text.lower()


# Checker on #39, mutants H40-H44 (JON-1393 item 18): the parts of the prompt an agent
# acts on. Only these phrases are pinned, not the whole text.
PROMPT_PHRASES = {
    "H40 fields, in order": "Report each finding as rule_id / file / evidence / severity,",
    "H41 kb_version": "Note the kb_version the review used.",
    "H42 correctness rule_id": 'use rule_id "correctness" for a correctness problem no rule covers',
    "H43 no findings": 'If nothing is wrong, say "no findings".',
}


@pytest.mark.parametrize("phrase", PROMPT_PHRASES.values(), ids=PROMPT_PHRASES.keys())
def test_the_prompt_keeps_the_instructions_an_agent_acts_on(phrase: str) -> None:
    from jdad import server

    assert phrase in server.review_against_kb_prompt(changed_files="api/x.py", summary="x")


@pytest.mark.parametrize(
    "changed_files",
    ["api/x.py, a.sql", "api/x.py\na.sql", "api/x.py\n\n a.sql ,", " ,api/x.py,\n,a.sql\n"],
    ids=["commas", "newlines", "blank-line-and-trailing-comma", "blanks-everywhere"],
)
def test_the_prompt_splits_files_on_commas_and_newlines_and_drops_blanks(changed_files: str) -> None:
    """Checker on #39, mutant H44."""
    from jdad import server

    text = server.review_against_kb_prompt(changed_files=changed_files, summary="x")
    assert " The changed files are: api/x.py, a.sql. " in text


def test_the_prompt_asks_for_the_files_when_none_are_given() -> None:
    from jdad import server

    text = server.review_against_kb_prompt(changed_files=" \n , ", summary="x")
    assert "The changed files are" not in text
    assert " List the changed files from the diff." in text


def test_jdad_review_calls_the_tool_and_uses_the_format() -> None:
    text = (REPO_ROOT / "commands" / "jdad.md").read_text()
    section = text[text.index("## `review`") :]
    section = section[: section.index("\n## ", 1)]
    assert "review_against_kb" in section
    assert all(field in section for field in FINDING_FIELDS)
    assert 'phase="review"' in section
