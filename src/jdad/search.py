"""Ranked lexical search over KB rules: BM25, stdlib only (roadmap P3.1).

Each rule is one document: its text, its `applies_when` note, its section
heading, its tags and the words of its ID. Scores use Okapi BM25 (k1=1.2,
b=0.75) with the usual non-negative IDF. The index is built per query from
the parsed KB; the KB is small, and nothing is cached across requests.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass

K1 = 1.2
B = 0.75
MAX_LIMIT = 50
SNIPPET_CHARS = 90
# A concise response never exceeds this many UTF-8 bytes as JSON (roadmap
# P3.1): lower-ranked hits are dropped until it fits.
MAX_CONCISE_BYTES = 2048
# Keeps "n+1", "p95", "c#", "node.js" as single tokens.
TOKEN_RE = re.compile(r"[a-z0-9]+(?:[+#.][a-z0-9]+|\+)*")
STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "by", "do", "for", "from", "how", "i", "in", "is",
        "it", "its", "of", "on", "or", "so", "that", "the", "this", "to", "use", "used", "using",
        "what", "when", "where", "which", "with", "you", "your",
    }
)


def _stem(token: str) -> str:
    """A deliberately small suffix folder (not Porter): plurals, -ation,
    -ing/-ed, then a final -e, so "images"/"image", "queries"/"query",
    "caching"/"cache" and "invalidation"/"invalidate" meet."""
    if not token.isalpha():
        return token  # n+1, p95, node.js stay as they are
    if len(token) > 4 and token.endswith("ies"):
        token = token[:-3] + "y"
    elif len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        token = token[:-1]
    if len(token) > 7 and token.endswith("ation"):
        token = token[:-5] + "ate"
    for suffix in ("ing", "ed"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            token = token[: -len(suffix)]
            break
    if len(token) > 4 and token.endswith("e"):
        token = token[:-1]
    return token


def tokenize(text: str) -> list[str]:
    tokens = []
    for token in TOKEN_RE.findall(text.lower()):
        token = token.rstrip(".")
        if token and token not in STOPWORDS:
            tokens.append(_stem(token))
    return tokens


@dataclass(frozen=True)
class Doc:
    rule: object  # jdad.kb.Rule
    topic: str
    file: str
    heading: str
    tokens: tuple[str, ...]


def _documents(practices) -> list[Doc]:
    docs = []
    for practice in practices:
        for section in practice.sections:
            for rule in section.rules:
                words = " ".join(
                    [rule.text, rule.applies_when or "", section.heading, " ".join(section.tags), (rule.id or "").replace(".", " ").replace("-", " ")]
                )
                docs.append(Doc(rule, practice.topic, practice.relpath, section.heading, tuple(tokenize(words))))
    return docs


def idf(n: int, df: int) -> float:
    """BM25 inverse document frequency, the non-negative form:
    log(1 + (n - df + 0.5) / (df + 0.5))."""
    return math.log(1 + (n - df + 0.5) / (df + 0.5))


def _fit(hits: list[dict], max_bytes: int) -> list[dict]:
    """Drop the lowest-ranked hits until the JSON fits in max_bytes."""
    while hits and len(json.dumps(hits, ensure_ascii=False).encode("utf-8")) > max_bytes:
        hits = hits[:-1]
    return hits


def _snippet(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= SNIPPET_CHARS else text[: SNIPPET_CHARS - 1].rstrip() + "…"


def search(practices, query: str, tags: list[str] | None = None, limit: int = 10, response_format: str = "concise") -> list[dict]:
    if response_format not in ("concise", "detailed"):
        raise ValueError("response_format must be 'concise' or 'detailed'")
    terms = tokenize(query)
    if not terms:
        return []
    limit = max(1, min(int(limit), MAX_LIMIT))
    wanted = {t.strip().lower() for t in (tags or []) if t and t.strip()}
    docs = _documents(practices)
    if wanted:
        docs = [d for d in docs if wanted & {t.lower() for t in d.rule.tags}]
    if not docs:
        return []
    n = len(docs)
    avg_len = sum(len(d.tokens) for d in docs) / n or 1.0
    df = Counter(term for d in docs for term in set(d.tokens))
    scored = []
    for doc in docs:
        counts = Counter(doc.tokens)
        score = 0.0
        for term in set(terms):
            tf = counts.get(term, 0)
            if not tf:
                continue
            score += idf(n, df[term]) * tf * (K1 + 1) / (tf + K1 * (1 - B + B * len(doc.tokens) / avg_len))
        if score > 0:
            scored.append((round(score, 3), doc))
    # Highest score first; ties broken by rule ID so results are stable.
    scored.sort(key=lambda item: (-item[0], item[1].rule.id or ""))
    results = []
    for score, doc in scored[:limit]:
        hit = {"id": doc.rule.id, "topic": doc.topic, "heading": doc.heading, "snippet": _snippet(doc.rule.text), "score": score}
        if response_format == "detailed":
            hit |= {"file": doc.file, **{k: v for k, v in doc.rule.as_dict().items() if k != "id"}}
        results.append(hit)
    return _fit(results, MAX_CONCISE_BYTES) if response_format == "concise" else results
