# Harness and context engineering

Date checked: 2026-11-22.

## Anthropic: Building effective agents (Dec 19, 2024)

Source: https://www.anthropic.com/engineering/building-effective-agents

- "We recommend finding the simplest solution possible, and only increasing complexity when needed."
- Workflows (predefined paths) vs agents (model-directed). Patterns: prompt chaining, routing, parallelization, orchestrator-workers, evaluator-optimizer ("one LLM call generates a response while another provides evaluation and feedback in a loop").
- Invest in the agent-computer interface (tool design) as much as in prompts.

## Anthropic: Effective context engineering for AI agents (Sep 29, 2025)

Source: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents

- Write system prompts at the "right altitude": between brittle hard-coded logic and vague guidance.
- "Just in time" context: keep lightweight identifiers (paths, queries, links) and load data with tools at runtime. This enables progressive disclosure.
- Long-horizon techniques: compaction, structured note-taking (agentic memory outside the context window), sub-agent architectures.

## Anthropic: Writing effective tools for agents (Sep 11, 2025)

Source: https://www.anthropic.com/engineering/writing-tools-for-agents

- Prototype tools, then run an evaluation with realistic tasks and let an agent analyze the transcripts. Namespace tools. Optimize responses for token efficiency (concise vs detailed response formats).
- Applies directly to JDAD's MCP tools (P3.x).

## Anthropic: Effective harnesses for long-running agents (Nov 26, 2025)

Source: https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents

- Two failure modes: trying to one-shot the whole app, and a later session declaring the job done early.
- Fix: an **initializer** session writes `init.sh`, a progress file (`claude-progress.txt`), a feature list, and an initial commit; each **coding** session makes incremental progress on one feature and leaves a clean, mergeable state.
- Feature list in JSON with `"passes": false`; agents may only flip `passes`. "The model is less likely to inappropriately change or overwrite JSON files compared to Markdown files."
- Session start ritual: `pwd`, read git log and progress file, pick the highest-priority unfinished feature, run the basic end-to-end test first.
- Agents mark features done without end-to-end testing unless told to test "as a human user would" (browser automation helped a lot).

## Anthropic: Harness design for long-running application development (Mar 24, 2026)

Source: https://www.anthropic.com/engineering/harness-design-long-running-apps

- Three agents: **planner** (expands a 1–4 sentence prompt into a product spec), **generator** (one feature per sprint), **evaluator** (drives the running app with Playwright MCP and grades against criteria).
- Self-evaluation is lenient: "Separating the agent doing the work from the agent judging it proves to be a strong lever."
- **Sprint contract**: before code, generator and evaluator agree on what "done" means and how it will be verified. Agents hand off through files.
- Grading criteria turn taste into gradable terms; calibrate the evaluator with few-shot examples. Criteria wording steers output.

## OpenAI: Harness engineering (Feb 11, 2026)

Source: https://openai.com/index/harness-engineering/

- Five months, ~1M lines, ~1,500 PRs, zero manually-written code. "Humans steer. Agents execute."
- When something failed, ask "what capability is missing, and how do we make it both legible and enforceable for the agent?"
- "Give Codex a map, not a 1,000-page instruction manual." One big AGENTS.md failed: context is scarce, "too much guidance becomes non-guidance," "it rots instantly," and it is hard to verify. Instead a ~100-line AGENTS.md is "the table of contents" for a structured `docs/` system of record (design docs, exec plans active/completed, tech-debt tracker, product specs, references, `DESIGN.md`, `PLANS.md`, `RELIABILITY.md`, `SECURITY.md`, `QUALITY_SCORE.md`).
- Plans are first-class, checked-in artifacts with progress and decision logs.
- Docs are enforced mechanically: linters and CI check freshness and cross-links; a recurring "doc-gardening" agent opens fix-up PRs.
- "Anything it can't access in-context while running effectively doesn't exist." Push decisions from chat into the repo.
- Enforce invariants, not implementations: custom lints whose error messages "inject remediation instructions into agent context"; layered architecture with validated dependency directions; "parse data shapes at the boundary."
- App legibility: per-worktree bootable app, Chrome DevTools Protocol skills, ephemeral local logs/metrics/traces queryable by the agent.
- Agent-to-agent review loop until reviewers are satisfied (a "Ralph Wiggum Loop").
- "Golden principles" plus recurring background cleanup tasks work "like garbage collection" for drift.

## Spec-driven development

Sources: https://github.com/github/spec-kit, https://kiro.dev/docs/specs/, https://kiro.dev/docs/steering/

- Spec Kit flow: `/speckit-constitution` (project principles, once), then per feature `/speckit-specify` → `/speckit-plan` → `/speckit-tasks` → `/speckit-implement` → `/speckit-converge` until "Converged". It supports many agents and has presets for organizational standards.
- Kiro specs: `requirements.md` (user stories and acceptance criteria "in structured notation"), `design.md` (architecture, sequence diagrams, error handling, testing strategy), `tasks.md` (discrete, trackable tasks, run in dependency "waves"). Steering files `product.md`, `tech.md`, `structure.md`; Kiro also reads `AGENTS.md`.

## Verification loops and independent review

Sources: https://code.claude.com/docs/en/best-practices, the two Anthropic harness posts, the OpenAI post, and JDAD's own Checker practice.

- A single pass/fail command is the most useful line in an instructions file. JDAD's `./verify` already follows this.
- Enforce it: a `Stop` hook (Claude Code), CI on every PR, branch protection.
- Tests are the oracle. Agents must not edit or delete tests to pass (Anthropic: "It is unacceptable to remove or edit tests"). Checker already flags weakened tests.
- Separate reviewer, fresh context, scoped to spec and correctness, "skip style."
- PRs carry evidence (commands and output) and an explicit Unverified list. This is JDAD's existing Checker proof standard.

## Lessons files

- Claude docs: add to CLAUDE.md "when Claude makes the same mistake a second time" or "a code review catches something Claude should have known."
- OpenAI: "Review comments, refactoring pull requests, and user-facing bugs are captured as documentation updates or encoded directly into tooling. When documentation falls short, we promote the rule into code."
- JDAD rule: append to `LESSONS.md`; on the second occurrence promote it to an instructions line, a skill, a lint, or a hook.

## Borrow / skip

| Call | What | Why |
| --- | --- | --- |
| Borrow | Short `AGENTS.md` map + `docs/` system of record | Strongest primary-source evidence; matches JDAD's KB |
| Borrow | `PLAN.md` / exec plans as checked-in artifacts, with a sprint contract (done criteria + how verified) | Fixes one-shotting and early "done" |
| Borrow | JSON feature/task list where agents only flip status | Harder to corrupt than Markdown |
| Borrow | Separate evaluator (Checker) with criteria and evidence | Self-review is lenient |
| Borrow | Custom lint messages that carry remediation text | Turns taste into enforced, self-explaining rules |
| Borrow | Doc-gardening routine | Keeps the KB and templates fresh |
| Borrow | Lightweight spec trio (`DESIGN.md` with requirements and acceptance criteria, `PLAN.md`, task list) | Kiro/Spec Kit structure without adopting either tool |
| Skip | Adopting Spec Kit or Kiro wholesale | JDAD's golden path must work in four harnesses with plain files; borrow the artifacts, not the tool |
| Skip | "Zero human code" as a rule | OpenAI's experiment constraint, not a production requirement |
