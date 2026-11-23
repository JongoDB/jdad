---
title: "Best practices for Claude Code"
author: "Anthropic (Claude Code documentation)"
url: https://code.claude.com/docs/en/best-practices
format: docs
posted: unknown
retrieved: 2026-11-22
capture: read the page through a fetch tool (no byline or date shown); each item was checked against a short verbatim excerpt, and the excerpts are not kept here
items: 29
cite_as: cc-best-practices
---
# Anthropic: Best practices for Claude Code
- What is useful: what belongs in instruction files versus hooks and deny rules, how to give the agent a pass/fail check and ask for evidence, and a checklist for unattended runs. Most of it carries over to other coding agents.
- What is missing: no byline or date (it is living documentation, so items may change), Claude Code-specific commands and settings throughout, and team CI setup is on a separate page.
## The 29 items
1. Put guarantees in hooks, deny rules or managed settings; the instruction file is guidance the model can override.
2. If a line in the instruction file keeps being missed despite emphasis, it belongs in a hook.
3. Leave out of the instruction file whatever the agent could find by reading the code.
4. Write a specific prompt: name the file, describe the symptom, and say what fixed looks like.
5. Hand over existing material (file references, screenshots, piped output) instead of describing it.
6. For a vague feature, have the agent interview you until it could write a spec, save it, and build from it in a fresh session.
7. Keep the instruction file short: commands, misleading code locations, decisions made outside the repo, and anything corrected twice.
8. Keep personal preferences in a local, gitignored instruction file.
9. Scope directory-specific rules with a path filter so they load only when the agent works there.
10. Put team procedures in skills, and mark workflows with side effects so only a person can start them.
11. Use an existing CLI where there is one, add MCP servers otherwise, and turn off the ones you don't need, since each adds context.
12. Give the agent a check that comes back pass or fail, and put the command that runs it in the instruction file.
13. Ask for evidence (the command it ran and its output, or the screenshot), not just a claim that tests pass.
14. Review against the spec and say "skip style", since a reviewer asked for problems will always find some.
15. Use a Stop hook to block the turn from ending until a check passes.
16. Put "never" rules in deny rules, which hold in every permission mode, and enable the sandbox for OS-level limits.
17. Rules match tool calls, not intent: a read deny rule doesn't catch a script that opens the file.
18. Keep the enforced set small; every hook and deny rule sometimes fires when it shouldn't and needs maintenance.
19. Give review subagents read-only tools and ask for short summaries back.
20. A fresh subagent can be slower than doing the task in place, because it has to re-gather context.
21. Clear the context between unrelated tasks.
22. After two failed corrections, clear the context and write a better prompt instead of a third correction.
23. Checkpoints don't restore files changed only by shell commands, so they complement git rather than replace it.
24. Before an unattended run, confirm the done criteria, how it checks itself, the allowed scope, the stop limits, and who approves the result.
25. Try a scripted batch on three files first, fix the prompt, then run the rest.
26. Before a scheduled cloud task runs, protect main with a branch rule the task can't bypass.
27. Give each parallel task its own worktree.
28. A second session, which hasn't seen the code being written, is an easy independent reviewer.
29. Drop ALL CAPS and "IMPORTANT" emphasis: current models follow plain wording, and emphasis makes them over-apply the rule.
