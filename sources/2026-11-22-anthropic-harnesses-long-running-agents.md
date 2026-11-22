---
title: "Effective harnesses for long-running agents"
author: "Justin Young (Anthropic)"
url: https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
format: article
posted: 2025-11-26
retrieved: 2026-11-22
capture: read the page through a fetch tool; each item was checked against a short verbatim excerpt, and the excerpts are not kept here
items: 12
cite_as: anthropic-harnesses
---
# Anthropic (Justin Young): Effective harnesses for long-running agents
- What is useful: a concrete two-agent setup for multi-session builds (an initializer, then coding agents that do one feature per session) and the state they hand over: a feature list, a progress file, a setup script and git history.
- What is missing: no measured results or comparisons, no templates for the progress file or setup script, and it is scoped to full-stack web apps; it leaves open whether one general agent beats a multi-agent setup.
## The 12 items
1. Use an initializer agent, with its own prompt, for the first context window, and a coding agent for every later session.
2. Have the initializer write a script that starts the development environment, a progress log, and an initial git commit.
3. Have the initializer write a complete feature list with every feature initially marked failing.
4. Coding agents may only change a feature's pass status; removing or editing tests is not allowed.
5. Keep the feature list in JSON, which the model is less likely to rewrite than Markdown.
6. Work on one feature per session.
7. Commit progress with descriptive messages and summarize it in the progress file, so bad changes can be reverted.
8. End each session in a clean state: code fit to merge to main, without major bugs, and documented.
9. Start each session by reading the git log, the progress file and the feature list, then pick the highest-priority unfinished feature.
10. Run a basic end-to-end check before starting new work, so existing breakage is found first.
11. Test end to end with browser automation, as a user would; with unit tests or curl alone the model marked features done that didn't work.
12. Mark a feature passing only after careful testing.
