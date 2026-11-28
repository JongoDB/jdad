# KB schema: practice files and rules

Roadmap P1.2 (JON-1333). `jdad lint-kb` enforces everything here (`src/jdad/lint.py`, structure checks), and `src/jdad/kb.py` parses it. Source files have frontmatter described in [ingestion.md](ingestion.md).

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
- **Tags:** one or more from the [table below](#tags). A rule inherits its section's tags, and `get_checklist(tags)` selects sections by them.
- **A section contains only rules and blank lines.** Explanations belong in the rule text or in an `Applies when:` line.

## Tags

| Tag | Scope | Not to be confused with |
| --- | --- | --- |
| `frontend` | Browser and UI code: rendering, assets, bundles, client state | `ux` (what the user experiences) |
| `backend` | Server code: request handling, jobs, outbound calls | `design` (the shape of an API or system) |
| `db` | Schemas, queries, indexes, migrations, data-side caching | |
| `infra` | Hosting, networking, CDN, containers, deploys | `ci` (the pipeline that runs checks) |
| `observability` | Logs, metrics, traces, alerting, real-user monitoring | |
| `testing` | What tests check and how: unit, integration, end-to-end, load | `ci` (where and when tests run) |
| `security` | Authentication, authorization, secrets, input handling, trust boundaries | `supply-chain` (what you pull in) |
| `supply-chain` | Dependencies, lockfiles, pinning, update bots, build provenance | `security` (your own code and config) |
| `ci` | Pipelines and required checks: workflows, gates, release automation | `testing` |
| `process` | How agents and people work: planning, review, verification, instruction files | |
| `design` | API and architecture decisions: interfaces, boundaries, data contracts | `backend` (implementation) |
| `ux` | User-facing behaviour and copy: flows, messages users see, accessibility | `frontend` (implementation) |

Tag a section with every tag a reader would filter by; a rule about rate-limiting a login endpoint is `[backend] [security]`. Jon approved the last six on 2026-11-22 (P2.3).

## A rule

A rule is a `- ` bullet at the start of a line:

```
- <text> (<citation>) {#<id>}
  <optional continuation lines, indented>
  Applies when: <optional condition, indented>
  Phase: <optional: plan, review and/or ship, indented>
```

| Part | Required | Format |
| --- | --- | --- |
| Text | yes | One instruction. Split combined advice into separate rules so each has one ID and one citation |
| Citation | yes | `(src: <source> #n)` or `(src: <source> #n, #m)` when it came from a source, or `(KB addition)` when it didn't (Rule zero in `CLAUDE.md`). It sets `origin`: `source` or `kb-addition`. `<source>` is a source's `cite_as`, and every `#n` must be within its `items` and appear once ([ingestion.md](ingestion.md)); the lint checks all three |
| ID | yes | `{#<prefix>.<area>.<slug>}`: lowercase letters, digits and hyphens, at least two dot-separated segments, unique across the KB, and the same `<prefix>` for every rule in a file (`perf` for `performance.md`). IDs are permanent: don't renumber or reuse them; retire a rule by deleting it |
| Continuation | no | Indented lines join the rule's text. The citation and ID end the rule's last text line |
| Applies when | no | An indented `Applies when: …` line, for rules that are easy to over-apply. Shown in checklists and returned as `applies_when` |
| Phase | no | An indented `Phase: plan, review` line: the checklist phases the rule belongs to, any of `plan`, `review` and `ship` (case and spacing don't matter). A rule with no `Phase:` line is in every phase. Returned as `phases`. The lint rejects an unknown or repeated phase, an empty line, and a second `Phase:` line on one rule |

Not allowed (lint `rule-format`): nested bullets, numbered items, prose in a section, rules before the first section, sections with no rules. The parser still keeps that text, attached to a rule or reported, so nothing vanishes from a checklist silently, but the KB must not depend on it.

## What the tools return

- `get_checklist(tags, phase?)`: Markdown checkboxes, one per rule, grouped under the section headings: `- [ ] <id>: <text> (<source URL> #n)`, where the URL is the cited source's `url` and `#n` the cited item numbers (rules from one source share its URL), or `(KB addition)` for a rule with no source. An Applies-when note stays in the text as ` _Applies when: …_`. With `phase` (`plan`, `review` or `ship`), only rules marked for that phase or with no `Phase:` line, and a `Phase:` line in the header. `kb://checklists/<tag>` returns the same text as `get_checklist([tag])`.
- `search_practices(query, tag?)`: each hit has `rules: [{id, text, tags, citation, origin, applies_when, phases}]` alongside the section's `heading` and raw `body`.
- `get_practice(topic)` and `kb://practices/<name>`: the file as written.

## Changing the format

Change this file, `kb.py`, the lint checks and their tests in one PR, then migrate every practice file in the same PR so `./verify` stays green.
