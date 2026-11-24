"""Duplicate and near-duplicate rules (roadmap P2.2, JON-1362)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jdad.cli import main
from jdad.dupes import THRESHOLD, kb_dupes, normalise, pair_scores
from jdad.kb import KnowledgeBase

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((REPO_ROOT / "tests" / "fixtures" / "dupes" / "pairs.json").read_text())


def _scores(label: str) -> list[float]:
    """Score each labeled pair, with IDF over every text in the fixture."""
    texts = sorted({t for key in ("duplicate", "paraphrase", "distinct") for pair in FIXTURE[key] for t in pair})
    index = {t: i for i, t in enumerate(texts)}
    scores = pair_scores(texts)
    out = []
    for a, b in FIXTURE[label]:
        i, j = sorted((index[a], index[b]))
        out.append(1.0 if i == j else scores[(i, j)])
    return out


def test_fixture_has_every_label() -> None:
    assert len(FIXTURE["duplicate"]) >= 5
    assert len(FIXTURE["paraphrase"]) >= 10
    assert len(FIXTURE["distinct"]) >= 10
    assert len(FIXTURE["kb_distinct"]) >= 5


def test_every_exact_duplicate_is_reported() -> None:
    assert all(score >= THRESHOLD for score in _scores("duplicate"))


def test_paraphrase_recall_is_at_least_0_8() -> None:
    scores = _scores("paraphrase")
    recall = sum(score >= THRESHOLD for score in scores) / len(scores)
    assert recall >= 0.8, f"recall {recall:.2f} at {THRESHOLD}: {sorted(scores)}"


def test_no_distinct_pair_is_reported() -> None:
    scores = _scores("distinct")
    assert max(scores) < THRESHOLD, sorted(scores)


def test_no_pair_labeled_distinct_in_the_kb_is_reported() -> None:
    reported = {(a, b) for _score, a, b in kb_dupes(REPO_ROOT, THRESHOLD)}
    ids = {r.id for doc in KnowledgeBase(REPO_ROOT).practices() for s in doc.sections for r in s.rules}
    for a, b in FIXTURE["kb_distinct"]:
        assert a in ids and b in ids, f"stale fixture: {a} or {b} is no longer a rule"
        assert tuple(sorted((a, b))) not in reported


def test_normalising_ignores_case_spacing_and_punctuation() -> None:
    assert normalise("Set a  timeout, on EVERY call!") == normalise("set a timeout on every call")
    assert pair_scores(["Paginate every list endpoint.", "paginate every list endpoint"])[(0, 1)] == 1.0
    assert pair_scores(["Paginate every list endpoint.", "Version every API."])[(0, 1)] < THRESHOLD
    # The tokenizer keeps "n+1" whole, so only the normalised-text check makes these equal.
    assert pair_scores(["Avoid N+1 queries.", "avoid n 1 queries"])[(0, 1)] == 1.0


def _kb(root: Path, rules: list[str]) -> Path:
    (root / "practices").mkdir(parents=True)
    (root / "sources").mkdir()
    lines = [f"- {text} (KB addition) {{#t.a.r{n}}}" for n, text in enumerate(rules)]
    (root / "practices" / "t.md").write_text("# T\n## A [backend]\n" + "\n".join(lines) + "\n")
    return root


def test_cli_reports_pairs_and_always_exits_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _kb(tmp_path, ["Paginate every list endpoint.", "paginate every list endpoint", "Batch writes in one transaction."])
    assert main(["kb", "dupes", "--root", str(root)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out == ["1.000  t.a.r0  t.a.r1", f"jdad kb dupes: 1 candidate pair(s) at or above {THRESHOLD}"]
    assert main(["kb", "dupes", "--root", str(root), "--threshold", "1.0"]) == 0  # at θ counts
    assert capsys.readouterr().out.splitlines()[0] == "1.000  t.a.r0  t.a.r1"
    assert main(["kb", "dupes", "--root", str(root), "--threshold", "1.01"]) == 0
    assert capsys.readouterr().out.splitlines() == ["jdad kb dupes: 0 candidate pair(s) at or above 1.01"]


def test_verify_prints_the_report_without_gating_on_it() -> None:
    verify = (REPO_ROOT / "verify").read_text()
    assert "uv run --frozen jdad kb dupes || true" in verify


def test_pairs_come_best_first(tmp_path: Path) -> None:
    root = _kb(tmp_path, ["Cache expensive queries.", "Cache expensive queries on write.", "Cache expensive queries."])
    scores = [score for score, _a, _b in kb_dupes(root, 0.0)]
    assert len(scores) == 3 and scores == sorted(scores, reverse=True) and scores[0] == 1.0 > scores[-1]


# ---- Checker's #34 follow-ups (JON-1363) ----


def test_every_duplicate_case_differs_as_text() -> None:
    """A pair of identical strings tests nothing the normaliser does."""
    assert all(a != b for a, b in FIXTURE["duplicate"])


def test_golden_score_pins_the_formula() -> None:
    """Hand-computed TF-IDF cosine for two texts sharing one of two words.

    n = 2; df(alpha) = 2, df(beta) = df(gamma) = 1. With idf = ln((1 + n) / (1 + df)) + 1:
    idf(alpha) = 1, idf(beta) = idf(gamma) = ln(3/2) + 1 = 1.405465. Each vector is
    (1, 1.405465) normalised, so the cosine is 1 / (1 + 1.405465**2) = 0.336097.
    """
    assert pair_scores(["alpha beta", "alpha gamma"]) == {(0, 1): 0.336}
    assert pair_scores(["alpha beta", "gamma delta"]) == {(0, 1): 0.0}


def _ordered_kb(root: Path, ids: list[str]) -> Path:
    (root / "practices").mkdir(parents=True)
    (root / "sources").mkdir()
    lines = [f"- Rule number {n} about {rid}. (KB addition) {{#{rid}}}" for n, rid in enumerate(ids)]
    (root / "practices" / "t.md").write_text("# T\n## A [backend]\n" + "\n".join(lines) + "\n")
    return root


def test_scores_are_rounded_before_the_threshold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A raw 0.5996 is reported as 0.6, so it counts at θ = 0.6."""
    from jdad import dupes

    monkeypatch.setattr(dupes, "similarity", lambda a, b: 0.5996)
    root = _ordered_kb(tmp_path, ["t.a.one", "t.a.two"])
    assert kb_dupes(root, 0.6) == [(0.6, "t.a.one", "t.a.two")]
    assert dupes.report(root, 0.6)[0] == "0.600  t.a.one  t.a.two"


def test_equal_scores_are_ordered_by_rule_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ties break on the IDs, sorted within each pair, whatever the file order."""
    from jdad import dupes

    monkeypatch.setattr(dupes, "similarity", lambda a, b: 0.7)
    root = _ordered_kb(tmp_path, ["t.z.last", "t.m.mid", "t.a.first"])
    assert kb_dupes(root, 0.6) == [
        (0.7, "t.a.first", "t.m.mid"),
        (0.7, "t.a.first", "t.z.last"),
        (0.7, "t.m.mid", "t.z.last"),
    ]
