---
title: "Harness design for long-running application development"
author: "Prithvi Rajasekaran (Anthropic)"
url: https://www.anthropic.com/engineering/harness-design-long-running-apps
format: article
posted: 2026-03-24
retrieved: 2026-11-22
capture: read the page through a fetch tool; each item was checked against a short verbatim excerpt, and the excerpts are not kept here
items: 20
cite_as: anthropic-harness-design
---
# Anthropic (Prithvi Rajasekaran): Harness design for long-running application development
- What is useful: a planner, generator and evaluator split; a skeptical evaluator that uses the running app and grades against written criteria with hard thresholds; done-criteria agreed before coding; and re-testing every harness piece as models change.
- What is missing: no setup for an existing repo (instruction files, test commands), no exact prompts, thresholds or file formats, and the examples are greenfield builds; costs are given only for those runs.
## The 20 items
1. Separate the agent doing the work from the agent judging it.
2. Tune a standalone evaluator to be skeptical; that is far easier than making the generator critical of its own work.
3. For long tasks, use context resets (a fresh agent with a structured handoff), not only compaction.
4. Make the handoff file carry enough state for the next agent to pick the work up cleanly.
5. Turn subjective quality into gradable criteria that encode stated principles.
6. Give the same criteria to the generator and the evaluator.
7. Calibrate the evaluator with few-shot examples and detailed score breakdowns.
8. Let the evaluator use the live app (a browser tool) before it scores.
9. Have a planner expand a short prompt into a spec of deliverables, kept high level, because early technical errors cascade.
10. Have the generator and evaluator agree what done means, and how it will be tested, before any code is written.
11. Pass information between agents through files.
12. Give each criterion a hard threshold; if any one falls below it, the work fails and goes back with feedback.
13. Have the evaluator test like a user: click through the running app and check API responses and database state.
14. Tune the evaluator by reading its logs and fixing its prompt where its judgment diverges from yours.
15. Untuned, the model is a poor QA agent: it notices problems and then talks itself into approving.
16. Every harness component encodes an assumption about what the model can't do alone, and those assumptions go stale.
17. Remove components one at a time and measure the effect, to find which are load-bearing.
18. Start with the simplest solution and add complexity only when needed.
19. A separate evaluator is worth its cost only when the task is beyond what the model does reliably alone.
20. Re-examine the harness when a new model arrives: remove what is no longer load-bearing and add what is newly possible.
