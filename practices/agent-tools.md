# Agent tools (designing tools and MCP servers for agents)
Rules for the tools an agent calls: which to build, what they return, how they're described, and how to evaluate them. Rule format: [docs/kb-schema.md](../docs/kb-schema.md).
## Choosing tools [design] [backend]
- Build a few tools for high-impact workflows instead of wrapping every API endpoint. (src: anthropic-tools #10) {#tools.choose.few-targeted}
- Prefer a task-level tool, such as a search, over one that lists everything. (src: anthropic-tools #11) {#tools.choose.search-over-list}
- Fold a multi-step lookup the agent always repeats into one tool. (src: anthropic-tools #12) {#tools.choose.consolidate}
- Give each tool one clear purpose that no other tool overlaps. (src: anthropic-tools #13) {#tools.choose.distinct-purpose}
- Prefix related tool names by service and resource. (src: anthropic-tools #14) {#tools.choose.namespace}
  Applies when: an agent sees tools from more than one server or service.
## Responses [design] [backend]
- Return high-signal fields, such as names and types, and leave out low-level identifiers the agent can't use. (src: anthropic-tools #15) {#tools.respond.high-signal}
- Let the agent choose a concise or a detailed response format. (src: anthropic-tools #16) {#tools.respond.format-choice}
- Bound large responses with pagination, filtering or truncation, with sensible defaults. (src: anthropic-tools #18) {#tools.respond.bound-size}
- When a response is truncated, say how to get the rest efficiently, such as with narrower searches. (src: anthropic-tools #19) {#tools.respond.truncation-hint}
- Make error messages say what went wrong and how to fix the call, not an opaque code or traceback. (src: anthropic-tools #20) {#tools.respond.actionable-errors}
## Descriptions [design]
- Describe each tool the way you would to a new teammate, spelling out implicit context and niche terms. (src: anthropic-tools #21) {#tools.describe.new-hire}
- Name parameters unambiguously, such as user_id rather than user. (src: anthropic-tools #22) {#tools.describe.unambiguous-params}
- Annotate tools that reach the open world or make destructive changes. (src: anthropic-tools #24) {#tools.describe.annotations}
  Applies when: the tools are served over MCP.
## Evaluate [design] [testing]
- Prototype tools quickly and try them locally before settling the design. (src: anthropic-tools #1) {#tools.eval.prototype-first}
- Evaluate tools on realistic, multi-step tasks with verifiable outcomes. (src: anthropic-tools #2, #3) {#tools.eval.realistic-tasks}
- Track tool calls, errors, runtime and tokens, not only task success. (src: anthropic-tools #4) {#tools.eval.track-metrics}
- Read the agents' evaluation transcripts, including what they leave out. (src: anthropic-tools #6) {#tools.eval.read-transcripts}
- Keep a held-out task set so tool changes don't overfit the evaluation. (src: anthropic-tools #9) {#tools.eval.held-out}
- Measure description changes in the evaluation, since small edits can change results a lot. (src: anthropic-tools #23) {#tools.eval.measure-descriptions}
