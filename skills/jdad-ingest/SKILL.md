---
name: jdad-ingest
description: Use when asked to add, ingest or mine a video, article, talk or thread into the JDAD knowledge base while working in a checkout of the JDAD repo - recording it under sources/, folding its practices into practices/ with citations and rule IDs, and regenerating the skills. Outside the JDAD repo, it only routes the link to Daisy.
metadata:
  generated: jdad build from catalog/skills/jdad-ingest/SKILL.md; do not edit
---

# JDAD ingest

The full runbook is in `docs/ingestion.md` ("Runbook"); this is the checklist. The rule format is in `docs/kb-schema.md`.

## First: is this the JDAD repo?

Check that `practices/`, `sources/` and `sources/_TEMPLATE.md` exist at the repo root. If they don't, write nothing: say that sources are added by Daisy, and ask the user to send her the link (the same as `/jdad add`).

## Checklist

1. Branch from an up-to-date `main`: `kb/<cite_as>`. One source per branch and PR.
2. Watch or read the whole source yourself. No transcript step: don't run a transcript tool or save a transcript or the article text anywhere.
3. Extract the tools, resources, practices and recommendations worth using, numbered 1 to N, one line each (short quotes, close paraphrase or timestamps). Nothing the source doesn't say.
4. Copy `sources/_TEMPLATE.md` to `sources/<retrieved>-<cite_as>-<slug>.md`. Fill every frontmatter field, then what is useful, what is missing, `## The N items` and the list.
5. Dedupe each item against the KB with `search_practices` before writing a rule.
6. Add rules to `practices/<topic>.md`: one instruction per rule, `(src: <cite_as> #n)`, a new `{#<prefix>.<area>.<slug>}` ID, tagged sections, `Applies when:` where a rule is easy to over-apply. Anything not from the source is labelled `(KB addition)`.
7. Copy the practice file's rule lines into `catalog/skills/jdad-<topic>/SKILL.md` and run `uv run jdad build`. Never edit `skills/` or `generated/` by hand.
8. Bump the version in all five files: patch for a source or rules, minor for a new topic or tool.
9. Run `uv run jdad lint-kb` and `./verify`, and check the new entry through `list_sources`, a search or checklist, and `kb_version`.
10. Push and open the PR with the R-flow-6 sections: the Linear card, What changed and why (link, what was added or deduplicated), Evidence (`./verify` output) and an Unverified list. Then post the Linear note with the head SHA. Don't merge it yourself.

## Never in the repo

- Full transcripts or article text.
- Claude Code session transcripts or agent logs (session `.jsonl` files, `.claude/projects/`, `.remember/`), or anything copied from them.
- Secrets, tokens or keys.
