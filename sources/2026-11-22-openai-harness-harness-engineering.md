---
title: "Harness engineering: leveraging Codex in an agent-first world"
author: "Ryan Lopopolo (OpenAI)"
url: https://openai.com/index/harness-engineering/
format: article
posted: 2026-02-11
retrieved: 2026-11-22
capture: read the page through a fetch tool; each item was checked against a short verbatim excerpt, and the excerpts are not kept here
items: 21
cite_as: openai-harness
---
# OpenAI (Ryan Lopopolo): Harness engineering
- What is useful: the repo as the agent's system of record, a short AGENTS.md as a map over a structured docs/ tree, and mechanical checks (linters, CI, recurring cleanup agents) that keep that knowledge and the architecture honest.
- What is missing: the tooling is OpenAI-specific (Codex, Chrome DevTools, a local log and metrics stack); almost no code; no failure rates or cost data; the post warns its merge philosophy and autonomy results don't carry over to low-throughput teams without similar investment.
## The 21 items
1. When an agent fails, ask what capability is missing (tool, guardrail, doc) and fix the environment; trying harder is almost never the fix.
2. Break large goals into smaller building blocks (design, code, review, test) and have the agent build those first.
3. Have the agent review its own changes locally, request agent reviews, and iterate until those reviewers are satisfied.
4. Make the app bootable per git worktree, so the agent can launch and drive one instance per change.
5. Give the agent browser and runtime access (DOM snapshots, screenshots) so it can reproduce bugs and validate fixes itself.
6. Expose logs, metrics and traces to the agent through a local observability stack that is ephemeral per worktree.
7. Keep AGENTS.md short, about 100 lines, as a map with pointers into a structured docs/ directory.
8. Use progressive disclosure: a small, stable entry point that tells the agent where to look next.
9. Treat plans as versioned files: light plans for small changes, execution plans with progress and decision logs for complex work.
10. Put the knowledge the agent needs into the repo; anything it can't discover there doesn't exist for it.
11. Run a recurring doc-gardening agent that finds stale documentation and opens fix-up PRs.
12. Validate the docs with dedicated linters and CI jobs: freshness, cross-links and structure.
13. Enforce invariants, not implementations: state the constraint (for example, parse data at the boundary) and leave the method open.
14. Enforce a layered architecture and its dependency directions with custom linters and structural tests.
15. Write lint error messages that tell the agent how to fix the violation.
16. Prefer well-known, stable dependencies the agent can model; sometimes reimplementing a small helper in-repo is better.
17. Capture review comments and user bugs as doc updates or tooling, and promote a rule into code when the doc isn't enough.
18. Keep merge gates minimal and PRs short-lived, re-running flaky tests rather than blocking (the post says this would be irresponsible at low throughput).
19. Encode "golden principles" as mechanical rules and run recurring background agents that open small cleanup PRs.
20. Pay technical debt down continuously in small increments rather than in bursts.
21. Humans steer: prioritize work, turn user feedback into acceptance criteria, and validate outcomes.
