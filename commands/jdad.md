---
description: Consult JDAD (Jon's agentic-dev knowledge base) to plan, review, apply performance rules, or file a new source.
argument-hint: plan | review | perf | add <url>
---

You are running the JDAD `/jdad` command. Route on the first word of `$ARGUMENTS`. The rest of the argument string is the task or URL.

Use the jdad MCP tools when they are available: `list_topics`, `search_practices`, `get_practice`, `get_checklist`, `list_sources`, `get_source`, and `kb_version`. Cite KB rules by their rule ID (for example `perf.db.n-plus-one`) in any plan, review or PR.

## `plan` — `/jdad plan [task]`

1. Read the current task (the remainder of `$ARGUMENTS`, plus the conversation and repo).
2. Call `list_topics`, then `get_checklist` with `phase="plan"` and the tags that apply (`frontend`, `backend`, `db`, `infra`, `observability`, `testing`, `security`, `supply-chain`, `ci`, `process`, `design`, `ux`). If the tags are unclear, `search_practices` first.
3. Write a short plan that includes the matching checklist and cite each rule you'll follow by its rule ID. Do not invent rules that are not in the KB, and do not apply a rule whose tag does not fit.
4. Call `kb_version` and mention the SHA and newest-entry date in the plan.

## `review` — `/jdad review [what]`

1. Review the named work (or the current diff) against the KB.
2. Call `review_against_kb` with the changed file paths and a one-line summary of the change. It infers the tags from the paths and returns the review checklist for those tags, the rules that match the summary, a rubric and the findings format. Add `tags` if the paths don't show them; for more rules, call `get_checklist` with `phase="review"`, or `get_practice` for a topic you rely on.
3. Follow the rubric: correctness first, then the rules that apply; skip style. Report each finding as `rule_id / file / evidence / severity` (blocker, major or minor). Cite the KB rule by its rule ID, and give evidence from the diff. Use `correctness` as the rule_id for a correctness problem no rule covers. "No findings" is a valid result.
4. Note `kb_version` so the review is pinned to a SHA.

## `perf` — `/jdad perf [what]`

1. Load the performance topic: `get_practice` with `performance`, and/or use the `jdad-performance` skill.
2. Apply Rule zero: measure first, fix the top bottleneck, re-measure, and put before/after numbers in the PR. Do not shotgun every rule.
3. Use `get_checklist` with the performance-related tags that apply (`frontend`, `backend`, `db`, `infra`, `observability`, `testing`).

## `add` — `/jdad add <url>`

Do not add the source to the knowledge base yourself from this command.

Tell the user to send the URL to Daisy (DevOps Lead) so it can be pulled into `sources/` and folded into `practices/`. Repeat the URL back so it is easy to forward. If `$ARGUMENTS` has no URL, ask for one.

## Unknown or missing argument

If `$ARGUMENTS` is empty or the first word is not one of `plan`, `review`, `perf`, or `add`, say so briefly and list those four subcommands with a one-line description each.
