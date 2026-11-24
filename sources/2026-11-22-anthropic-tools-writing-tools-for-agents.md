---
title: "Writing effective tools for agents - with agents"
author: "Ken Aizawa (Anthropic)"
url: https://www.anthropic.com/engineering/writing-tools-for-agents
format: article
posted: 2025-09-11
retrieved: 2026-11-22
capture: read the page through a fetch tool; each item was checked against a short verbatim excerpt, and the excerpts are not kept here
items: 24
cite_as: anthropic-tools
---
# Anthropic (Ken Aizawa): Writing effective tools for agents - with agents
- What is useful: an evaluation-driven loop for tools (prototype, evaluate on realistic tasks, refine with an agent's help, check against held-out tasks) and concrete design rules: fewer, task-level tools, high-signal responses, bounded output, actionable errors and clear descriptions. It applies directly to MCP servers like this repo's.
- What is missing: no code or harness for the evaluations, results only as charts, and little on security, permissions or auth. The one hard number is that Claude Code caps a tool response at 25,000 tokens by default.
## The 24 items
1. Stand up a quick prototype of the tools and try them locally, since it's hard to predict which tools agents will find ergonomic.
2. Base evaluation tasks on real uses and realistic data, not simplistic sandboxes; strong tasks may need multiple tool calls, potentially dozens.
3. Pair each task with a verifiable outcome, without verifiers so strict that they reject correct answers.
4. Track more than accuracy: tool-call runtime, number of calls, token use and tool errors.
5. Have evaluation agents write their reasoning and feedback before their tool calls.
6. Read the agents' feedback and raw evaluation transcripts; what they leave out can matter more than what they say.
7. Read metrics as diagnostics: many redundant calls suggest tuning pagination or limits; many invalid-parameter errors suggest clearer descriptions or examples.
8. Give evaluation transcripts to a coding agent to refactor many tools at once and keep their descriptions consistent.
9. Use held-out test tasks so improvements don't overfit the evaluation.
10. Don't just wrap existing API endpoints; build a few targeted tools for high-impact workflows.
11. Prefer a task-level tool (search_contacts, message_contact) over a list-everything tool (list_contacts).
12. Consolidate frequently chained, multi-step operations into one tool, such as get_customer_context instead of several get and list calls.
13. Give each tool a clear, distinct purpose; too many or overlapping tools distract agents.
14. Namespace related tools with common prefixes by service and by resource.
15. Return high-signal fields such as names and file types, and leave out low-level identifiers (uuids, image URLs, mime types).
16. Expose a response_format option so the agent can choose concise or detailed output.
17. Choose the response structure (XML, JSON, Markdown) by evaluation; no one format is best.
18. Add pagination, range selection, filtering or truncation with sensible defaults where responses can be large.
19. When truncating, steer the agent toward efficient strategies, such as many small targeted searches.
20. Make error messages actionable instead of opaque codes or tracebacks.
21. Write tool descriptions as you would for a new hire, making implicit context and niche terms explicit.
22. Use unambiguous parameter names and strict data models, such as user_id rather than user.
23. Small refinements to tool descriptions can have large effects; measure them in evaluation.
24. For MCP servers, use tool annotations to disclose open-world access or destructive changes.
