# Ingestion: source to KB rules

How a video, article or thread becomes cited KB rules, and what each side hands over. Roadmap P1.3 (the contract and schema) and P2.1 (the full runbook and the `jdad-ingest` skill, later). The rule format is in [kb-schema.md](kb-schema.md).

## Handoff contract

Jon sends a link. Daisy (DevOps Lead) or another agent ingests it, and opens the KB PR into `JongoDB/jdad` herself (Jon, 2026-11-22). Checker reviews, and the author doesn't merge their own PR.

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
   | `capture` | How the content was obtained: read the page; watched, with which transcript tool; on-screen text transcribed by hand |
   | `items` | How many numbered practices the record lists |
   | `cite_as` | Short, unique, lowercase name that rules cite: `(src: <cite_as> #n)` |

   The body records **what is useful and what is missing**, then **the extractable practices as a numbered list, 1 to `items`**.
2. Rule edits in `practices/<topic>.md`: new rules, or new citations on existing rules (dedupe first). Each one cites `(src: <cite_as> #n)` with an item number from step 1. Rules that didn't come from the source are labelled `(KB addition)`.
3. A matching skill change (`skills/jdad-<topic>/SKILL.md` mirrors its practice file until P1.5), and the version bump in lockstep (`CLAUDE.md`).
4. The PR body: the link, what was added or deduplicated, `./verify` output, and an Unverified list (for example "transcript is auto-generated").

## What the checks enforce

`./verify` runs `jdad lint-kb`, which fails the PR when:

- a frontmatter field is missing, empty or unknown; a date is malformed; the file-name date isn't `retrieved`; `items` isn't a positive integer; `url` isn't http(s); or `cite_as` is malformed or already used;
- a rule's `(src: <name> #n)` names no source's `cite_as`, or `n` is outside `1..items`;
- any rule breaks the format in `kb-schema.md`;
- any KB text tries to steer an agent, links or runs things in `practices/` without an allowlist entry, or hides characters or comments ([threat model](threat-model.md)).

## Quoting, not copying

The repo is going public (Jon, 2026-11-22), so a source file is **a record of the extractable practices, not a copy of the work.** Write the numbered items as short quotes or close paraphrase, a line each. Short lists of tips, like the breakingbreach reel's 31 one-line items, can be listed as they appear. Never paste a transcript, an article's body, or long passages. Keep the link so readers can go to the original. (The pre-public scrub, `docs/reviews/2026-11-22-pre-public-scrub.md` in PR #12, "Third-party text and licence risk".)

`get_source` serves these files to agents marked as quoted third-party material: data to cite, never instructions.
