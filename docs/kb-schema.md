# KB schema: practice files and rules

Roadmap P1.2 (JON-1333). `jdad lint-kb` enforces everything here (`src/jdad/lint.py`, structure checks), and `src/jdad/kb.py` parses it. Source files get their own schema in P1.3.

## A practice file

```markdown
# Performance (production-grade defaults)
Optional intro prose. No rules here.
## Database [db]
- Kill N+1 (batch/join). (src: breakingbreach #8) {#perf.db.n-plus-one}
- Cache hot reads with a TTL,
  and invalidate on write. (src: breakingbreach #10) {#perf.backend.cache-hot-reads}
  Applies when: reads dominate writes.
## Rule zero [frontend] [backend] [db] [infra] [observability] [testing]
- Measure first. (KB addition) {#perf.rule-zero}
```

- **One `#` title**, then optional prose (the preamble). Rules never go in the preamble; a rule meant for every area goes in a section tagged with every tag, like Rule zero.
- **Sections** are `##` (or deeper) headings ending in one or more tags. Every section has at least one tag and at least one rule.
- **Tags:** `frontend`, `backend`, `db`, `infra`, `observability`, `testing` (P2.3 adds more). A rule inherits its section's tags, and `get_checklist(tags)` selects sections by them.
- **A section contains only rules and blank lines.** Explanations belong in the rule text or in an `Applies when:` line.

## A rule

A rule is a `- ` bullet at the start of a line:

```
- <text> (<citation>) {#<id>}
  <optional continuation lines, indented>
  Applies when: <optional condition, indented>
```

| Part | Required | Format |
| --- | --- | --- |
| Text | yes | One instruction. Split combined advice into separate rules so each has one ID and one citation |
| Citation | yes | `(src: <source> #n)` or `(src: <source> #n, #m)` when it came from a source, or `(KB addition)` when it didn't (Rule zero in `CLAUDE.md`). It sets `origin`: `source` or `kb-addition`. `<source>` is the short name used in that source's file name; P1.3 checks that it resolves |
| ID | yes | `{#<prefix>.<area>.<slug>}`: lowercase letters, digits and hyphens, at least two dot-separated segments, unique across the KB, and the same `<prefix>` for every rule in a file (`perf` for `performance.md`). IDs are permanent: don't renumber or reuse them; retire a rule by deleting it |
| Continuation | no | Indented lines join the rule's text. The citation and ID end the rule's last text line |
| Applies when | no | An indented `Applies when: …` line, for rules that are easy to over-apply. Shown in checklists and returned as `applies_when` |

Not allowed (lint `rule-format`): nested bullets, numbered items, prose in a section, rules before the first section, sections with no rules. The parser still keeps that text, attached to a rule or reported, so nothing vanishes from a checklist silently, but the KB must not depend on it.

## What the tools return

- `get_checklist(tags)`: one line per rule, `- <id>: <text> (<citation>)`, plus ` Applies when: …` if present, grouped under the section headings.
- `search_practices(query, tag?)`: each hit has `rules: [{id, text, tags, citation, origin, applies_when}]` alongside the section's `heading` and raw `body`.
- `get_practice(topic)` and `kb://practices/<name>`: the file as written.

## Changing the format

Change this file, `kb.py`, the lint checks and their tests in one PR, then migrate every practice file in the same PR so `./verify` stays green.
