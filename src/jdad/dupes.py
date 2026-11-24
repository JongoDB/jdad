"""Duplicate and near-duplicate rules (roadmap P2.2).

Each rule's text becomes a TF-IDF vector over `jdad.search.tokenize` tokens
(stopwords dropped, a small stemmer), and every pair of rules is scored by
cosine similarity. Two texts that are equal once case, spacing and
punctuation are ignored always score 1.0. Pairs at or above the threshold
are candidates for a human to merge or cite together; the report never
changes the KB. Stdlib only, offline.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from itertools import combinations
from pathlib import Path

from jdad.search import tokenize

# The cutoff θ, chosen from the labeled pairs in tests/fixtures/dupes/pairs.json:
# every duplicate scores 1.0, 13 of 15 paraphrases score at least 0.601, and
# the highest distinct pair scores 0.580. At 0.65 paraphrase recall falls to
# 0.73. Rerun the fixture before moving it.
THRESHOLD = 0.6


def normalise(text: str) -> str:
    """Lower case, punctuation dropped, whitespace collapsed."""
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def _vectors(texts: list[str]) -> list[dict[str, float]]:
    token_lists = [tokenize(t) for t in texts]
    n = len(texts)
    df = Counter(term for tokens in token_lists for term in set(tokens))
    vectors = []
    for tokens in token_lists:
        counts = Counter(tokens)
        vec = {term: tf * (math.log((1 + n) / (1 + df[term])) + 1) for term, tf in counts.items()}
        norm = math.sqrt(sum(w * w for w in vec.values())) or 1.0
        vectors.append({term: w / norm for term, w in vec.items()})
    return vectors


def similarity(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(w * b.get(term, 0.0) for term, w in a.items())


def pair_scores(texts: list[str]) -> dict[tuple[int, int], float]:
    """Score every pair (i < j) of texts, with IDF taken over all of them."""
    vectors = _vectors(texts)
    normal = [normalise(t) for t in texts]
    scores = {}
    for i, j in combinations(range(len(texts)), 2):
        score = 1.0 if normal[i] == normal[j] else similarity(vectors[i], vectors[j])
        scores[(i, j)] = round(min(score, 1.0), 3)
    return scores


def kb_dupes(root: Path | str, threshold: float) -> list[tuple[float, str, str]]:
    """Rule pairs in the KB at or above `threshold`, best first, then by ID."""
    from jdad.kb import KnowledgeBase

    rules = [rule for doc in KnowledgeBase(root).practices() for section in doc.sections for rule in section.rules]
    scores = pair_scores([rule.text for rule in rules])
    found = [(score, *sorted((rules[i].id or "", rules[j].id or ""))) for (i, j), score in scores.items() if score >= threshold]
    return sorted(found, key=lambda item: (-item[0], item[1], item[2]))


def report(root: Path | str, threshold: float = THRESHOLD) -> list[str]:
    pairs = kb_dupes(root, threshold)
    lines = [f"{score:.3f}  {a}  {b}" for score, a, b in pairs]
    lines.append(f"jdad kb dupes: {len(pairs)} candidate pair(s) at or above {threshold}")
    return lines
