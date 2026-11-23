---
name: jdad-workflow
description: Use when setting up or running coding agents on a repo, or planning, verifying, reviewing or handing off agent work - instruction files (AGENTS.md, CLAUDE.md), specs and done-criteria, pass/fail checks, evaluator or reviewer agents, progress notes and session handoffs, hooks and deny rules, worktrees, unattended runs, and keeping a harness current. Applies Jon's JDAD agentic-workflow checklist.
metadata:
  generated: jdad build from catalog/skills/jdad-workflow/SKILL.md; do not edit
---

# JDAD agentic workflow

These rules come from `practices/agentic-workflow.md` in the JDAD knowledge base. Prefer the jdad MCP tools (`get_practice` with `agentic-workflow`, or `get_checklist` with `process`) when they are available, so you are on the latest SHA. Cite rules in the plan and the PR by rule ID (for example `wf.verify.evidence`) and source.

Each rule ends with its citation and its ID.

## The repo is the system of record [process]
- Put every decision an agent needs into the repo as docs, plans, practices or lints; what it can't find there doesn't exist for it. (src: openai-harness #10) {#wf.repo.system-of-record}
- Keep the root instruction file short: a map that points to deeper docs, not a manual. (src: openai-harness #7, #8) {#wf.repo.short-map}
- Leave out of instruction files whatever the agent can learn by reading the code. (src: cc-best-practices #3) {#wf.repo.omit-discoverable}
- Write down anything you have had to correct twice. (src: cc-best-practices #7) {#wf.repo.correct-twice}
- Write instructions plainly, without all-caps emphasis, which makes models over-apply them. (src: cc-best-practices #29) {#wf.repo.plain-wording}
- Keep personal preferences in a local, gitignored instruction file. (src: cc-best-practices #8) {#wf.repo.local-preferences}
- Check plans into the repo, with progress and decision logs for complex work. (src: openai-harness #9) {#wf.repo.plans-in-repo}
  Applies when: the work spans more than one session or PR.
## Plan and scope [process]
- Turn a vague request into a written spec before building, then build from the spec in a fresh session. (src: cc-best-practices #6) {#wf.plan.spec-first}
  Applies when: the feature is vague or large.
- Specify deliverables and acceptance criteria, and leave the implementation path to the agent. (src: anthropic-harness-design #9) {#wf.plan.deliverables-not-path}
- Agree what done means, and how it will be checked, before any code is written. (src: anthropic-harness-design #10) {#wf.plan.agree-done}
- Work on one feature at a time. (src: anthropic-harnesses #6) {#wf.plan.one-feature}
- In a task prompt, name the file, describe the symptom, and say what fixed looks like. (src: cc-best-practices #4) {#wf.plan.specific-prompt}
- Hand the agent existing material (files, screenshots, command output) instead of describing it. (src: cc-best-practices #5) {#wf.plan.hand-over-material}
## Verify [process] [testing]
- Give the agent a check that comes back pass or fail, and put its command in the instruction file. (src: cc-best-practices #12) {#wf.verify.pass-fail-check}
- Ask for evidence of verification: the command run and its output, or a screenshot. (src: cc-best-practices #13) {#wf.verify.evidence}
- Test end to end the way a user would, not only with unit tests or raw HTTP calls. (src: anthropic-harnesses #11) {#wf.verify.end-to-end}
  Applies when: the change has a user-facing surface.
- Run a basic end-to-end check before starting new work, so existing breakage is found first. (src: anthropic-harnesses #10) {#wf.verify.check-before-work}
- Mark work done only after it has been tested. (src: anthropic-harnesses #12) {#wf.verify.done-after-test}
- Don't let a coding agent remove or edit the acceptance tests; it may only record whether they pass. (src: anthropic-harnesses #4) {#wf.verify.no-test-edits}
## Make the app legible to the agent [process] [testing] [observability]
- Make the app bootable per worktree, so the agent can run and drive one instance per change. (src: openai-harness #4) {#wf.legible.boot-per-worktree}
  Applies when: agents work on changes in parallel.
- Give the agent browser access to the running app, so it can reproduce bugs and validate fixes itself. (src: openai-harness #5) {#wf.legible.browser-access}
  Applies when: the app has a UI.
- Give the agent the app's logs, metrics and traces. (src: openai-harness #6) {#wf.legible.observability}
## Review [process]
- Have a separate agent judge the work, not the agent that did it. (src: anthropic-harness-design #1, #19) {#wf.review.separate-judge}
  Applies when: the task is beyond what the model does reliably alone.
- Prompt the reviewer to be skeptical, since an untuned model talks itself into approving. (src: anthropic-harness-design #2, #15) {#wf.review.skeptical}
- Tune the reviewer by reading its logs and correcting it where its judgment diverges from yours. (src: anthropic-harness-design #14) {#wf.review.tune-on-disagreement}
- Let the reviewer use the running app, its API and its data before it scores. (src: anthropic-harness-design #8, #13) {#wf.review.use-the-app}
- Grade against written criteria, and fail the work if any one criterion falls below its threshold. (src: anthropic-harness-design #5, #12) {#wf.review.criteria-thresholds}
- Review against the spec, and tell the reviewer to skip style. (src: cc-best-practices #14) {#wf.review.against-spec}
- Give review agents read-only tools and ask for short summaries back. (src: cc-best-practices #19) {#wf.review.read-only}
- Turn review comments and user bugs into doc updates or tooling so they don't recur. (src: openai-harness #17) {#wf.review.feed-back}
## Sessions and handoffs [process]
- Start each session by reading the git log, the progress notes and the task list. (src: anthropic-harnesses #9) {#wf.session.read-state}
- End each session with a descriptive commit and an updated progress note. (src: anthropic-harnesses #7) {#wf.session.commit-and-note}
- Leave the code fit to merge at the end of every session. (src: anthropic-harnesses #8) {#wf.session.clean-state}
- On the first session of a multi-session build, write a setup script, a progress log and a full feature list marked failing. (src: anthropic-harnesses #2, #3) {#wf.session.initializer}
  Applies when: a new project will take many sessions.
- Keep a task list that agents update in JSON rather than Markdown. (src: anthropic-harnesses #5) {#wf.session.json-task-list}
  Applies when: agents edit status fields in the list.
- For long tasks, reset the context with a structured handoff file rather than relying only on compaction. (src: anthropic-harness-design #3, #4) {#wf.session.reset-with-handoff}
- Clear the context between unrelated tasks. (src: cc-best-practices #21) {#wf.session.clear-between-tasks}
- After two failed corrections, start over with a better prompt instead of correcting a third time. (src: cc-best-practices #22) {#wf.session.restart-after-two}
- Keep committing to git; editor checkpoints miss files changed by shell commands. (src: cc-best-practices #23) {#wf.session.git-not-checkpoints}
## Enforce mechanically [process] [ci] [security]
- Put rules that must always hold in hooks, deny rules or CI, not in instruction prose. (src: cc-best-practices #1) {#wf.enforce.guarantees-in-checks}
- Move an instruction that keeps being missed into a hook or a check. (src: cc-best-practices #2) {#wf.enforce.missed-line-to-check}
- Back deny rules with a sandbox, because they match tool calls, not what a script does. (src: cc-best-practices #16, #17) {#wf.enforce.sandbox}
- Keep the enforced set small, since every hook and deny rule misfires sometimes and needs upkeep. (src: cc-best-practices #18) {#wf.enforce.small-set}
- Block the end of an agent's turn until the check passes. (src: cc-best-practices #15) {#wf.enforce.stop-gate}
- Protect the main branch with a rule that unattended agents can't bypass. (src: cc-best-practices #26) {#wf.enforce.protect-main}
## Architecture and cleanup [process] [design] [ci]
- Enforce invariants, and leave the implementation open. (src: openai-harness #13) {#wf.arch.invariants}
- Enforce layering and dependency directions with custom linters and structural tests. (src: openai-harness #14) {#wf.arch.structural-lints}
- Write lint messages that tell the agent how to fix the violation. (src: openai-harness #15) {#wf.arch.remediation-messages}
- Prefer well-known, stable dependencies the agent can model. (src: openai-harness #16) {#wf.arch.boring-deps}
- Check docs in CI for freshness, cross-links and structure. (src: openai-harness #12) {#wf.arch.docs-lint}
- Run recurring agents that find stale docs and drifted code and open small fix-up PRs. (src: openai-harness #11, #19) {#wf.arch.gardening-agents}
- Pay technical debt down continuously in small increments. (src: openai-harness #20) {#wf.arch.continuous-debt}
## Unattended and parallel runs [process] [security]
- Before an unattended run, define done, the self-check, the allowed scope, the stop limits and who approves the result. (src: cc-best-practices #24) {#wf.unattended.preflight}
- Try a batch run on a few items first, fix the prompt, then run the rest. (src: cc-best-practices #25) {#wf.unattended.small-batch-first}
- Give each parallel task its own worktree. (src: cc-best-practices #27) {#wf.unattended.worktree-per-task}
- Mark workflows with side effects so only a person can start them. (src: cc-best-practices #10) {#wf.unattended.manual-side-effects}
- Turn off tools and servers the agent doesn't need, since each adds context. (src: cc-best-practices #11) {#wf.unattended.trim-tools}
## Harness upkeep [process]
- When an agent fails, add the missing tool, guardrail or doc instead of retrying harder. (src: openai-harness #1) {#wf.harness.fix-environment}
- Start with the simplest harness, and add a piece only when it is needed. (src: anthropic-harness-design #18) {#wf.harness.start-simple}
- Re-test each harness component when a new model arrives, and remove those that are no longer load-bearing. (src: anthropic-harness-design #16, #20) {#wf.harness.retest-on-new-model}
- Remove harness components one at a time and measure the effect. (src: anthropic-harness-design #17) {#wf.harness.ablate-one-at-a-time}
