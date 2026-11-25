"""review_against_kb (roadmap P3.4, JON-1367): rules inferred from the changed files,
a rubric and a findings format. The server does no model calls; the agent reviews."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from mcp import Client

from jdad.kb import KNOWN_TAGS, KnowledgeBase
from jdad.review import FINDING_FIELDS, SEVERITIES, build_review, infer_tags

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
    ],
)
def test_path_rules(path: str, tags: set[str]) -> None:
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


def test_an_unknown_tag_is_an_error_that_names_it() -> None:
    with pytest.raises(ValueError, match="'frontnd'"):
        build_review(KnowledgeBase(FIXTURE), ["api/x.py"], "x", tags=["frontnd"])


def test_no_tags_means_no_rules_and_a_note() -> None:
    review = build_review(KnowledgeBase(FIXTURE), ["README.md"], "docs only")
    assert review["tags"] == [] and review["checklist"] == "" and review["relevant"] == []
    assert "tags" in review["note"]


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


def test_findings_format_has_the_four_fields() -> None:
    fmt = build_review(KnowledgeBase(FIXTURE), ["api/x.py"], "x")["findings_format"]
    assert FINDING_FIELDS == ("rule_id", "file", "evidence", "severity")
    assert fmt["fields"] == list(FINDING_FIELDS)
    assert fmt["severity"] == list(SEVERITIES) == ["blocker", "major", "minor"]
    example = fmt["example"]
    assert all(f"{field}:" in example for field in ("rule", "file", "evidence", "severity"))


def test_review_echoes_the_summary_and_pins_the_kb_version() -> None:
    review = build_review(KnowledgeBase(FIXTURE), ["api/x.py"], "  add retries  ")
    assert review["summary"] == "add retries"
    assert review["changed_files"] == ["api/x.py"]
    assert "kb_version" in review


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
async def test_the_prompt_names_the_tool_and_the_format(client: Client) -> None:
    prompts = {p.name for p in (await client.list_prompts()).prompts}
    assert "review-against-kb" in prompts
    from jdad import server

    text = server.review_against_kb_prompt(changed_files="api/x.py, a.sql", summary="add retries")
    assert "review_against_kb" in text and "api/x.py" in text and "add retries" in text
    assert all(field in text for field in FINDING_FIELDS)
    assert "skip style" in text.lower()


def test_jdad_review_calls_the_tool_and_uses_the_format() -> None:
    text = (REPO_ROOT / "commands" / "jdad.md").read_text()
    section = text[text.index("## `review`") :]
    section = section[: section.index("\n## ", 1)]
    assert "review_against_kb" in section
    assert all(field in section for field in FINDING_FIELDS)
    assert 'phase="review"' in section
