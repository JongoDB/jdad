# Community setups worth borrowing from

Date checked: 2026-11-22. Star counts and last-push dates come from the GitHub API on that date.

| Repo | Stars | What it is |
| --- | --- | --- |
| [obra/superpowers](https://github.com/obra/superpowers) | ~324k | Skills framework and dev methodology; one source installed into Claude Code, Codex, Cursor, Grok Build, Gemini CLI and others |
| [anthropics/skills](https://github.com/anthropics/skills) | ~199k | Anthropic's public Agent Skills, including `skill-creator`, `mcp-builder`, `webapp-testing`, `frontend-design` |
| [github/spec-kit](https://github.com/github/spec-kit) | ~151k | Spec-driven development toolkit (constitution → specify → plan → tasks → implement → converge) |
| [hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code) | ~59k | Curated list of Claude Code skills, hooks, commands, workflows |
| [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official) | ~48k | Anthropic's official plugin directory (the `claude-plugins-official` marketplace) |
| [wshobson/agents](https://github.com/wshobson/agents) | ~43k | 93 plugins (agents, skills, commands) for Claude Code, Codex, Cursor, OpenCode, Copilot and more, with adapters and a `plugin-eval` scorer |
| [VoltAgent/awesome-agent-skills](https://github.com/VoltAgent/awesome-agent-skills) | ~37k | 1000+ Agent Skills from vendor teams and the community |
| [openai/skills](https://github.com/openai/skills) | ~29k | OpenAI's skills catalog for Codex |
| [trailofbits/skills](https://github.com/trailofbits/skills) | ~8k | Security skills: differential review, insecure defaults, supply-chain risk audit, static analysis, property-based and mutation testing |
| [anthropics/claude-code-security-review](https://github.com/anthropics/claude-code-security-review) | ~7k | GitHub Action for diff-aware AI security review on PRs |
| [xai-org/plugin-marketplace](https://github.com/xai-org/plugin-marketplace) | ~0.3k | xAI's official Grok Build marketplace (`.grok-plugin/marketplace.json`, SHA-pinned sources) |

## What to borrow from each

1. **obra/superpowers**: the workflow skill set (`brainstorming` → `writing-plans` → `subagent-driven-development` / `executing-plans` → `test-driven-development` → `verification-before-completion` → `requesting-code-review` → `finishing-a-development-branch`, plus `systematic-debugging` and `using-git-worktrees`). Its README describes plans "clear enough for an enthusiastic junior engineer with poor taste, no judgement, no project context, and an aversion to testing to follow." It ships one source to many harnesses, which is exactly JDAD's distribution problem. **Borrow:** the plan-quality bar, the verification-before-completion gate, per-harness install docs. **Don't copy:** the skills themselves. JDAD should depend on or recommend Superpowers rather than fork it, and only add JDAD-specific opinions (KB checklists, Checker proof standard).
2. **anthropics/skills**: `skill-creator` (authoring plus evals) and `mcp-builder`. **Borrow:** the eval-driven skill iteration loop for JDAD's catalog; `webapp-testing` as the reference for "test as a user would."
3. **github/spec-kit**: the constitution idea (project principles written once) and the converge loop. **Borrow:** JDAD's `VISION.md` principles act as the constitution; `DESIGN.md` → `PLAN.md` → tasks mirrors specify → plan → tasks. **Skip:** the `specify` CLI and its catalogs.
4. **wshobson/agents**: proof that one source tree can feed Claude Code, Codex (native skills plus generated TOML agents) and Cursor (`.cursor-plugin/marketplace.json`), with model-alias mapping per harness and a static `plugin-eval score` for skills. **Borrow:** the adapter architecture for the JDAD compiler, and static skill scoring in `./verify`.
5. **trailofbits/skills**: security review skills. **Borrow:** recommend `differential-review`, `insecure-defaults` and `supply-chain-risk-auditor` in JDAD's security pack (P5.3) instead of writing our own.
6. **anthropics/claude-code-security-review**: **Borrow:** as an optional CI job in the JDAD CI template for repos that have an API key.
7. **hesreallyhim/awesome-claude-code** and **VoltAgent/awesome-agent-skills**: discovery lists. **Borrow:** as ingestion sources for Daisy, under the normal source → practice rules.
8. **xai-org/plugin-marketplace**: **Borrow:** SHA-pinned marketplace entries (supply-chain hygiene) for JDAD's own marketplace when it lists external plugins.
9. **anthropics/claude-plugins-official** and **openai/skills**: **Borrow:** the official plugin and skill layout conventions as the conformance reference for JDAD's compiler output.

## Unverified

- Star counts move daily; numbers are rounded from the GitHub API on 2026-11-22.
- Quality of individual third-party skills was not audited. Anything JDAD recommends gets a review before it goes into a template (P5.3 covers how).
