"""Checklists v2 (roadmap P3.3, JON-1364): phases, checkbox lines with rule IDs
and citation URLs, and kb://checklists/{tag}."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from mcp import Client
from mcp.types import TextResourceContents

from jdad.kb import KNOWN_TAGS, PHASES, KnowledgeBase
from jdad.lint import lint_kb

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "checklists"
ITEM_RE = re.compile(r"^- \[ \] (\S+): (.+) \((https?://\S+ #\d+(?:, #\d+)*|KB addition)\)$")
TAGS = ["backend", "ci"]
EXPECTED = {
    None: ["app.api.paginate", "app.api.errors", "app.api.version", "app.api.timeouts", "app.release.full-suite", "app.release.measure"],
    "plan": ["app.api.paginate", "app.api.version", "app.api.timeouts", "app.release.measure"],
    "review": ["app.api.paginate", "app.api.errors", "app.api.timeouts"],
    "ship": ["app.api.timeouts", "app.release.full-suite", "app.release.measure"],
}


def items(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("- ")]


def ids(text: str) -> list[str]:
    return [ITEM_RE.match(line).group(1) for line in items(text)]


def test_fixture_lints_clean() -> None:
    assert lint_kb(FIXTURE) == []


def test_phases_are_plan_review_ship() -> None:
    assert PHASES == ("plan", "review", "ship")


@pytest.mark.parametrize("phase", [None, *PHASES])
def test_each_phase_selects_its_rules(phase: str | None) -> None:
    text = KnowledgeBase(FIXTURE).get_checklist(TAGS, phase=phase)
    assert ids(text) == EXPECTED[phase]
    if phase:
        assert f"Phase: {phase}" in text.splitlines()


@pytest.mark.parametrize("phase", [None, *PHASES])
def test_every_item_line_has_a_checkbox_id_and_citation(phase: str | None) -> None:
    for root in (FIXTURE, REPO_ROOT):
        lines = items(KnowledgeBase(root).get_checklist([], phase=phase))
        assert lines
        bad = [line for line in lines if not ITEM_RE.match(line)]
        assert not bad, bad[:3]


def test_citations_become_source_urls_and_kb_additions_say_so() -> None:
    lines = {ITEM_RE.match(line).group(1): line for line in items(KnowledgeBase(FIXTURE).get_checklist([]))}
    assert lines["app.api.paginate"] == "- [ ] app.api.paginate: Paginate every list endpoint. (https://example.com/guide #1)"
    assert lines["app.release.measure"] == "- [ ] app.release.measure: Measure before you optimise. (KB addition)"
    assert lines["app.api.timeouts"] == (
        "- [ ] app.api.timeouts: Set a timeout on every outbound call. "
        "_Applies when: the service calls other services._ (https://example.com/guide #4)"
    )


def test_unknown_phase_is_an_error() -> None:
    with pytest.raises(ValueError, match="phase"):
        KnowledgeBase(FIXTURE).get_checklist([], phase="deploy")


def test_rules_carry_their_phases() -> None:
    rules = {r.id: r for d in KnowledgeBase(FIXTURE).practices() for s in d.sections for r in s.rules}
    assert rules["app.api.paginate"].phases == ("plan", "review")
    assert rules["app.api.timeouts"].phases == ()
    assert rules["app.api.paginate"].as_dict()["phases"] == ["plan", "review"]


@pytest.mark.parametrize(
    ("phase_lines", "message"),
    [
        (["  Phase: deploy"], "unknown phase 'deploy'"),
        (["  Phase: plan, plan"], "phase 'plan' is listed twice"),
        (["  Phase: plan", "  Phase: review"], "more than one 'Phase:' line"),
        (["  Phase:"], "empty 'Phase:' line"),
    ],
)
def test_lint_rejects_bad_phase_lines(tmp_path: Path, phase_lines: list[str], message: str) -> None:
    (tmp_path / "practices").mkdir()
    (tmp_path / "sources").mkdir()
    body = "\n".join(["# T", "## A [backend]", "- Do a thing. (KB addition) {#t.a.thing}", *phase_lines, ""])
    (tmp_path / "practices" / "t.md").write_text(body)
    messages = [f.message for f in lint_kb(tmp_path) if f.check == "rule-format"]
    assert any(message in m for m in messages), messages


def test_phase_values_ignore_case_and_spacing(tmp_path: Path) -> None:
    (tmp_path / "practices").mkdir()
    (tmp_path / "sources").mkdir()
    (tmp_path / "practices" / "t.md").write_text("# T\n## A [backend]\n- Do a thing. (KB addition) {#t.a.thing}\n  phase:  Ship ,PLAN\n")
    rule = KnowledgeBase(tmp_path).practices()[0].sections[0].rules[0]
    assert rule.phases == ("ship", "plan")
    assert lint_kb(tmp_path) == []


@pytest.mark.anyio
async def test_checklist_resource_equals_the_tool_for_every_tag(client: Client) -> None:
    templates = await client.list_resource_templates()
    assert "kb://checklists/{tag}" in [t.uri_template for t in templates.resource_templates]
    kb = KnowledgeBase(REPO_ROOT)
    for tag in KNOWN_TAGS:
        resource = await client.read_resource(f"kb://checklists/{tag}")
        texts = [b.text for b in resource.contents if isinstance(b, TextResourceContents)]
        assert texts == [kb.get_checklist([tag])], tag


@pytest.mark.anyio
async def test_the_tool_forwards_phase(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KB_ROOT", str(FIXTURE))
    for phase in PHASES:
        result = await client.call_tool("get_checklist", {"tags": TAGS, "phase": phase})
        text = result.content[0].text
        assert ids(text) == EXPECTED[phase], phase


def _command_section(name: str) -> str:
    text = (REPO_ROOT / "commands" / "jdad.md").read_text()
    start = text.index(f"## `{name}`")
    end = text.find("\n## ", start + 1)
    return text[start : end if end != -1 else None]


@pytest.mark.parametrize("name", ["plan", "review"])
def test_jdad_plan_and_review_cite_rule_ids(name: str) -> None:
    section = _command_section(name)
    assert f'phase="{name}"' in section
    assert "rule ID" in section and "cite" in section.lower()


def test_kb_additions_are_spelled_the_same_whatever_the_source_case(tmp_path: Path) -> None:
    """The parser accepts '(kb addition)' in any case; the checklist always says '(KB addition)'."""
    (tmp_path / "practices").mkdir()
    (tmp_path / "sources").mkdir()
    (tmp_path / "practices" / "t.md").write_text("# T\n## A [backend]\n- Do a thing. (kb addition) {#t.a.thing}\n")
    assert items(KnowledgeBase(tmp_path).get_checklist([])) == ["- [ ] t.a.thing: Do a thing. (KB addition)"]


# ---- Checker's #35 follow-ups (JON-1363): pin the served output ----


@pytest.mark.parametrize("phase", [None, *PHASES])
def test_the_phase_header_appears_only_for_a_phase(phase: str | None) -> None:
    """No `Phase: None` (or any Phase line) without a phase; exactly one per topic with one."""
    text = KnowledgeBase(FIXTURE).get_checklist(TAGS, phase=phase)
    headers = [line for line in text.splitlines() if line.startswith("Phase:")]
    assert headers == ([f"Phase: {phase}"] if phase else [])


def test_the_full_served_text_for_a_phase() -> None:
    """The whole review checklist, byte for byte: headings with no rules in the phase are left out."""
    assert KnowledgeBase(FIXTURE).get_checklist(TAGS, phase="review") == (
        "# App practices\n"
        "Topic: app\n"
        "Tags: backend, ci\n"
        "Phase: review\n"
        "\n"
        "## API [backend]\n"
        "- [ ] app.api.paginate: Paginate every list endpoint. (https://example.com/guide #1)\n"
        "- [ ] app.api.errors: Return actionable errors. (https://example.com/guide #2)\n"
        "- [ ] app.api.timeouts: Set a timeout on every outbound call. "
        "_Applies when: the service calls other services._ (https://example.com/guide #4)\n"
    )


def test_a_phase_that_empties_every_section_returns_the_no_match_text(tmp_path: Path) -> None:
    (tmp_path / "practices").mkdir()
    (tmp_path / "sources").mkdir()
    (tmp_path / "practices" / "p.md").write_text("# P\n## A [db]\n- Index filters. (KB addition) {#p.a.index}\n  Phase: review\n")
    assert KnowledgeBase(tmp_path).get_checklist(["db"], phase="ship") == "No matching practice rules for tags: db.\n"


def test_apply_kb_asks_for_the_plan_phase() -> None:
    from jdad import server

    prompt = server.apply_kb()
    assert 'get_checklist with phase="plan"' in prompt
    assert "rule ID" in prompt


@pytest.mark.anyio
async def test_the_tool_schema_lists_the_phases(client: Client) -> None:
    tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    schema = tools["get_checklist"].input_schema
    phase = schema["properties"]["phase"]
    enums = [option.get("enum") for option in phase.get("anyOf", [phase]) if option.get("enum")]
    assert enums == [list(PHASES)], phase
    assert "phase" not in schema.get("required", [])


def test_a_phase_line_before_any_rule_is_stray_text_not_a_crash(tmp_path: Path) -> None:
    (tmp_path / "practices").mkdir()
    (tmp_path / "sources").mkdir()
    (tmp_path / "practices" / "p.md").write_text("# P\n## A [db]\n  Phase: plan\n- Index filters. (KB addition) {#p.a.index}\n")
    kb = KnowledgeBase(tmp_path)
    assert ids(kb.get_checklist(["db"], phase="ship")) == ["p.a.index"]  # the stray line gives the rule no phase
    findings = lint_kb(tmp_path)
    assert [(f.check, f.line, f.message) for f in findings] == [
        ("rule-format", 3, "indented text that belongs to no rule")
    ], findings


def test_citations_keep_their_item_numbers() -> None:
    """Checker (#35): every breakingbreach rule showed the same reel URL; the item number tells them apart."""
    lines = items(KnowledgeBase(REPO_ROOT).get_checklist(["frontend"]))
    cites = [ITEM_RE.match(line).group(3) for line in lines]
    sourced = [c for c in cites if c != "KB addition"]
    assert sourced and all(re.search(r" #\d+(, #\d+)*$", c) for c in sourced), sourced[:3]
    assert len(set(sourced)) == len(sourced), "two rules cite the same item"
