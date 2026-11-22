"""Ranked lexical search (roadmap P3.1): BM25 over rules."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jdad.kb import KnowledgeBase
from jdad.search import MAX_LIMIT, tokenize

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "search"
QUERIES = {k: v for k, v in json.loads((FIXTURE / "queries.json").read_text()).items() if not k.startswith("_")}
BROAD = "cache images index queries timeout bundle keyboard errors pagination migration retry"


@pytest.fixture(scope="module")
def kb() -> KnowledgeBase:
    return KnowledgeBase(FIXTURE)


def test_ten_queries_are_committed() -> None:
    assert len(QUERIES) == 10


@pytest.mark.parametrize(("query", "expected"), list(QUERIES.items()))
def test_expected_top_three_in_order(kb: KnowledgeBase, query: str, expected: list[str]) -> None:
    assert [hit["id"] for hit in kb.search_practices(query)][:3] == expected


def test_concise_response_with_limit_10_fits_in_2048_bytes(kb: KnowledgeBase) -> None:
    hits = kb.search_practices(BROAD, limit=10, response_format="concise")
    assert len(hits) == 10
    assert len(json.dumps(hits, ensure_ascii=False).encode("utf-8")) <= 2048
    assert set(hits[0]) == {"id", "topic", "heading", "snippet", "score"}


def test_repo_kb_concise_response_fits_too() -> None:
    hits = KnowledgeBase(REPO_ROOT).search_practices("cache images queries index tests slow api", limit=10)
    assert len(hits) == 10
    assert len(json.dumps(hits, ensure_ascii=False).encode("utf-8")) <= 2048


def test_detailed_adds_the_full_rule(kb: KnowledgeBase) -> None:
    hit = kb.search_practices("concurrent index", limit=1, response_format="detailed")[0]
    assert hit["id"] == "data.migrations.concurrent-index"
    assert hit["text"] == "Add an index concurrently on large tables."
    assert hit["applies_when"] == "the table has more than a million rows."
    assert hit["tags"] == ["db", "infra"] and hit["origin"] == "kb-addition"
    assert hit["file"] == "practices/data.md" and hit["topic"] == "data"


def test_scores_are_ranked_and_ties_break_by_id(kb: KnowledgeBase) -> None:
    hits = kb.search_practices("timeout for outbound calls")
    scores = [hit["score"] for hit in hits]
    assert scores == sorted(scores, reverse=True)
    tied = [hit["id"] for hit in hits if hit["score"] == hits[1]["score"]]
    assert tied == sorted(tied)


def test_tag_filters(kb: KnowledgeBase) -> None:
    assert {h["id"] for h in kb.search_practices("index", tags=["infra"])} == {"data.migrations.concurrent-index"}
    assert kb.search_practices("index", tag="infra") == kb.search_practices("index", tags=["infra"])
    assert kb.search_practices("keyboard", tags=["db"]) == []


def test_limits_and_empty_queries(kb: KnowledgeBase) -> None:
    assert len(kb.search_practices(BROAD, limit=1)) == 1
    assert len(kb.search_practices(BROAD, limit=0)) == 1  # clamped to 1
    assert len(kb.search_practices(BROAD, limit=10_000)) <= MAX_LIMIT
    assert kb.search_practices("") == []
    assert kb.search_practices("the and of") == []  # only stopwords
    assert kb.search_practices("zzzzz") == []
    with pytest.raises(ValueError):
        kb.search_practices("index", response_format="verbose")


def test_tokenizer_keeps_technical_tokens_and_folds_simple_suffixes() -> None:
    assert tokenize("N+1 queries, p95 latency in Node.js") == ["n+1", "query", "p95", "latency", "node.js"]
    assert tokenize("caching cache") == ["cach", "cach"]
    assert tokenize("invalidation invalidate") == ["invalidat", "invalidat"]
