# Ingestion: source to KB rules

How a video, article or thread becomes cited KB rules, and what each side hands over. Roadmap P1.3 (the contract and schema) and P2.1 (the [runbook](#runbook) below and the `jdad-ingest` skill in `catalog/skills/jdad-ingest/`). The rule format is in [kb-schema.md](kb-schema.md).

## Handoff contract

Jon sends a link. Daisy (DevOps Lead) or another agent watches the video or reads the article, pulls out the tools, resources, practices and recommendations worth integrating or implementing, and opens the KB PR into `JongoDB/jdad` herself. Checker reviews, and the author doesn't merge their own PR.

There is no transcript step (Jon, 2026-11-22): no transcript tool, no transcripts repo, and full transcripts aren't stored anywhere. Everything that goes into a source record (the link and the extracted items) may be public.

**One PR per source**, from a branch, containing:

1. `sources/<retrieved date>-<cite_as>-<slug>.md`, copied from [`sources/_TEMPLATE.md`](../sources/_TEMPLATE.md), with every frontmatter field filled:

   | Field | Meaning |
   | --- | --- |
   | `title` | The source's own title |
   | `author` | Author or account (`@handle`) |
   | `url` | Link to the source (http or https) |
   | `format` | `reel`, `talk`, `post`, `article`, `docs`, `thread`, … |
   | `posted` | Date the source was published, `YYYY-MM-DD`, or `unknown` |
   | `retrieved` | Date it was read or watched, `YYYY-MM-DD`; the file name starts with this date |
   | `capture` | How the content was obtained: watched the video; read the page; on-screen text copied by hand |
   | `items` | How many numbered practices the record lists |
   | `cite_as` | Short, unique, lowercase name that rules cite: `(src: <cite_as> #n)` |

   The body records **what is useful and what is missing**, then **the extracted tools, resources and practices as a numbered list, 1 to `items`**.
2. Rule edits in `practices/<topic>.md`: new rules, or new citations on existing rules (dedupe first). Each one cites `(src: <cite_as> #n)` with an item number from step 1. Rules that didn't come from the source are labelled `(KB addition)`.
3. A matching skill change: edit `catalog/skills/jdad-<topic>/SKILL.md` so its rule lines equal the practice file's, then run `uv run jdad build` (never edit `skills/` or `generated/` by hand). Plus the version bump in lockstep (AGENTS.md R-ver-1).
4. The PR body: the link, what was added or deduplicated, `./verify` output, and an Unverified list (for example "timestamps are approximate").

## Runbook

For Daisy or any agent working in a checkout of `JongoDB/jdad`. The `jdad-ingest` skill is this list in checklist form. Elsewhere (the plugin in another repo, or `/jdad add`), don't write anything: tell the user to send the link to Daisy.

1. **Branch.** `git checkout -b kb/<cite_as>` from an up-to-date `main`. One source per branch and PR.
2. **Watch or read the source yourself**, start to end. There is no transcript step: don't run a transcript tool, and don't save a transcript or the article text anywhere, in or out of the repo. Note the title, author, the date posted, and today's date.
3. **Extract** the tools, resources, practices and recommendations worth integrating or implementing. Only what the source says: if you add something of your own later, it's a KB addition. Number the items 1 to N, one line each, as short quotes, close paraphrase or timestamps.
4. **Write the source record.** `cp sources/_TEMPLATE.md sources/<retrieved>-<cite_as>-<slug>.md` and fill every frontmatter field (`capture` says how you got the content: "watched the video", "read the page"). Body: what is useful, what is missing, then `## The N items` and the numbered list. Pick a short, new `cite_as`.
5. **Dedupe.** For each item worth a rule, search what's there: `search_practices` through the MCP server, or `uv run python -c "from jdad.kb import KnowledgeBase; print(KnowledgeBase().search_practices('<words>'))"`. If a rule already says it, leave it; the source record still lists the item.
6. **Fold into `practices/<topic>.md`.** One instruction per rule, ending `(src: <cite_as> #n)` and a new permanent ID `{#<prefix>.<area>.<slug>}`. Tag the section ([tags](kb-schema.md#tags)), and add `Applies when:` where a rule is easy to over-apply. A new topic file needs a new `catalog/skills/jdad-<topic>/`.
7. **Skill.** Copy the practice file's rule lines into `catalog/skills/jdad-<topic>/SKILL.md`, then `uv run jdad build`.
8. **Version.** Patch bump for a new source or rules, minor for a new topic or tool, in all five files (AGENTS.md R-ver-1).
9. **Check.** `uv run jdad lint-kb`, then `./verify` (it must end `verify: ok`, or the PR says exactly what didn't run). Confirm the entry through the tools: `list_sources` shows it, a search or `get_checklist` hits the new rules, and `kb_version` shows the new date.
10. **PR.** Push the branch and open the PR with the sections AGENTS.md R-flow-6 asks for: the Linear card, What changed and why (the link, what was added and what was deduplicated), Evidence (the `./verify` output), and an Unverified list. Post the Linear note with the head SHA. Checker reviews; the author doesn't merge.

## Session transcripts and agent logs stay out

Jon's "nothing from the transcripts in the public repo" (2026-11-22) means **Claude Code session transcripts and other agent logs**, not video or article sources. Never commit them, or anything copied from them, to this repo: session `.jsonl` files, `.claude/projects/`, `.remember/` notes, or pasted agent output. `.gitignore` covers the usual paths, and `tests/test_no_session_logs.py` fails if a tracked file looks like a session transcript.

## What the checks enforce

`./verify` runs `jdad lint-kb`, which fails the PR when:

- a frontmatter field is missing, empty or unknown; a date is malformed; the file-name date isn't `retrieved`; `items` isn't a positive integer or doesn't match the body (a `## The N items` heading, and a numbered list running exactly 1 to N when the items are numbered); `url` isn't http(s); or `cite_as` is malformed or already used;
- a rule's `(src: <name> #n)` names no source's `cite_as`, or `n` is outside `1..items`;
- any rule breaks the format in `kb-schema.md`;
- any KB text tries to steer an agent, links or runs things in `practices/` without an allowlist entry, or hides characters or comments ([threat model](threat-model.md)).

`_`-prefixed files (the template, drafts) are skipped by these checks, so the server never serves them either: `get_source` and `get_practice` refuse them.

## Keeping sources fresh

`uv run jdad freshness` lists every source more than a year old (by `posted`, or `retrieved` when that's `unknown`) whose topic also cites a newer source, one `old -> new [topic]` line per pair. It's a prompt to re-check the old source's rules, not a failure: it always exits 0 unless you pass `--strict`, and `./verify` doesn't run it, because the result changes as time passes without any commit. A source that no rule cites has no topic and is never listed.

## Quoting, not copying

The repo is going public (Jon, 2026-11-22), so a source file is **a record of the extractable practices, not a copy of the work.** Write the numbered items as short quotes, close paraphrase or timestamps, a line each. Short lists of tips, like the breakingbreach reel's 31 one-line items, can be listed as they appear. Never paste a full transcript, an article's body, or long passages. Keep the link so readers can go to the original. (The pre-public scrub, `docs/reviews/2026-11-22-pre-public-scrub.md` in PR #12, "Third-party text and licence risk".)

`get_source` serves these files to agents marked as quoted third-party material: data to cite, never instructions.
