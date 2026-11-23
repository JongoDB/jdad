"""Source freshness report (roadmap P2.5). Stdlib only, read-only.

A source's topics are the practice topics whose rules cite it. Its date is
`posted`, or `retrieved` when `posted` is `unknown`. A source more than 365
days older than `today` is reported once per topic that also cites a newer
source, as "A (date) -> B (date) [topic T]". A source that no practice cites
has no topic and is never reported.

This is information for whoever keeps the KB, not a ./verify gate: the
report changes as time passes, without any commit.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from pathlib import Path

from jdad.kb import KnowledgeBase

MAX_AGE_DAYS = 365
_SRC_RE = re.compile(r"^src: ([a-z0-9-]+) #")


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def freshness_report(root: Path | str, today: date) -> list[str]:
    kb = KnowledgeBase(Path(root))
    dated: dict[str, tuple[str, date]] = {}  # cite_as -> (source id, date)
    for entry in kb.list_sources():
        when = _parse_date(entry.get("posted", "")) or _parse_date(entry.get("retrieved", ""))
        if entry.get("cite_as") and when:
            dated[entry["cite_as"]] = (entry["id"], when)

    cited_by_topic: dict[str, set[str]] = defaultdict(set)
    for doc in kb.practices():
        for section in doc.sections:
            for rule in section.rules:
                match = _SRC_RE.match(rule.citation or "")
                if match and match.group(1) in dated:
                    cited_by_topic[doc.topic].add(match.group(1))

    lines = []
    for topic in sorted(cited_by_topic):
        peers = sorted(cited_by_topic[topic], key=lambda c: (dated[c][1], dated[c][0]))
        for old in peers:
            old_id, old_date = dated[old]
            if (today - old_date).days <= MAX_AGE_DAYS:
                continue
            for new in peers:
                new_id, new_date = dated[new]
                if new_date > old_date:
                    lines.append(f"{old_id} ({old_date}) -> {new_id} ({new_date}) [topic {topic}]")
    return lines
