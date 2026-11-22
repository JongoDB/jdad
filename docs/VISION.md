# JDAD vision

JDAD (Jon-does-agentic-dev) is an opinionated way for coding agents to build professional, production-grade software. It packages that opinion so it works the same in Claude Code, Codex, Grok Build and Cursor: a cited knowledge base, an MCP server that serves it, a skills catalog, harness templates, a bootstrapper, and evals that prove it helps.

Research behind this page: [docs/research/](research/README.md). Decisions: [docs/adr/](adr/). Work plan: [ROADMAP.md](../ROADMAP.md).

## Principles

1. **The repo is the system of record.** If an agent can't read it in the repo, it doesn't exist. Decisions from chat, calls and videos land in the repo as docs, ADRs, practices or lints. ([OpenAI, harness engineering](research/harness-engineering.md))
2. **A map, not a manual.** `AGENTS.md` stays short (about 100 lines) and points to deeper docs. Procedures go in skills, area rules in path-scoped rules, facts in the instructions file. Context loads progressively.
3. **One source, every harness.** Write to the open floor (AGENTS.md, Agent Skills, MCP, Agent Plugins) once. Add a thin per-tool adapter only where a tool needs one. Never hand-maintain four copies.
4. **Plan before code.** Non-trivial work starts with a written design and plan that state what "done" means and how it will be verified (a sprint contract). One item per session; leave a clean, mergeable state.
5. **Every change has an oracle.** `./verify` returns pass or fail. Agents run it, CI runs it, and hooks enforce it. Tests are never weakened to pass.
6. **The author doesn't grade its own work.** A separate reviewer (Checker) with fresh context checks the work against the spec and the KB, scoped to correctness, and requires evidence.
7. **Deterministic where it must be, judgment everywhere else.** "Never" and "always" rules become hooks, deny rules, lints or CI. Everything else stays guidance the agent can weigh.
8. **Taste becomes mechanism.** A lesson goes into `LESSONS.md` the first time. The second time it gets promoted to a rule, skill, lint or hook, and lint messages explain the fix.
9. **Cite or label.** Every KB rule cites its source or is labeled a KB addition. Measure before optimizing.
10. **Secure and observable by default.** Least privilege for agents and CI, no secrets in repos, pinned dependencies, structured logs, traces and health checks from day one.
11. **Prove the opinions.** An opinion that doesn't measurably improve agent output in the eval suite gets revised or dropped.

## The golden path

The default loop for an agent building production software in a JDAD repo:

| Step | What the agent does | Artifact |
| --- | --- | --- |
| 0. Bootstrap | `jdad init` drops the harness into the repo (once) | `AGENTS.md`, `CLAUDE.md`, `VERIFY.md`, tool configs, `./verify` |
| 1. Orient | Read `AGENTS.md`, the roadmap or issue, `LESSONS.md`, recent git log | (none) |
| 2. Specify | Requirements and acceptance criteria; design for anything non-trivial | `DESIGN.md` or `docs/design/<feature>.md` |
| 3. Plan | Steps, risks, and the verification for each acceptance criterion; pull KB checklists (`/jdad plan`) | `PLAN.md` on the issue/card, with KB rule IDs cited |
| 4. Build | Small commits, tests first where they fit, one item at a time | Code and tests |
| 5. Verify | `./verify`, plus run the app the way a user would | Command output as evidence |
| 6. Review | Independent review against the spec and KB (`/jdad review`, Checker) | Review verdict |
| 7. Ship | PR with summary, evidence and an Unverified list | PR |
| 8. Learn | Record lessons; promote repeats; send new sources to the KB | `LESSONS.md`, KB PRs |

## Opinionated vs configurable

| Opinionated (JDAD decides) | Configurable (the project decides) |
| --- | --- |
| `AGENTS.md` is the canonical instructions file; `CLAUDE.md` imports it | Which tools a repo targets (`--tools claude,codex,cursor,grok`) |
| A `./verify` entry point that returns pass/fail and runs in CI | What `./verify` runs for the stack (language, test runner, linters) |
| Plan-first for non-trivial work, with acceptance criteria and verification per criterion | Where plans live (Linear card, GitHub issue, `docs/exec-plans/`) |
| Independent review before merge, with evidence and an Unverified list | Who reviews (Checker, a subagent, a human) |
| No secrets in repos; deny rules for secret files and destructive commands | Extra allow rules and the permission mode a person prefers |
| Pinned CI actions, least-privilege `permissions:`, dependency and secret scanning | Which scanners, and severity thresholds |
| Structured logs, traces and health checks in services | Observability vendor and backends |
| KB rules cite sources; KB additions are labeled | Which KB topics and tags a repo pulls in |
| Skills follow the Agent Skills spec | Personal skills and output styles |

## Lanes of output

| Lane | What it is | Today | Roadmap |
| --- | --- | --- | --- |
| **Knowledge base** | `sources/` (verbatim record per source) and `practices/` (tagged, cited rules); git is the database | One source, one topic (performance) | Schema, rule IDs, ingestion pipeline, dedupe, more topics (Phases 1, 2, 5) |
| **MCP server** | Read-only, offline `jdad-mcp`: stdio locally, streamable HTTP hosted with bearer auth | 7 tools, a resource, a prompt | Ranked and optional semantic search, checklists, `review_against_kb`, template resources and `bootstrap_repo` (Phase 3) |
| **Skills catalog** | One canonical Agent Skills source, compiled to each tool's location and format | `jdad-performance` plus the `/jdad` command | `catalog/` and `jdad build` (Phase 1), more skills per pack (Phase 5) |
| **Harness templates** | `AGENTS.md`, `CLAUDE.md`, `DESIGN.md`, `PLAN.md`, `VERIFY.md`, `LESSONS.md`, hooks, settings, permissions, MCP config per tool | None | Phase 4 |
| **Scaffolder** | `jdad init` / `jdad sync` / `jdad doctor` to install and maintain the harness in any repo | None | Phase 4 |
| **Evals** | A small benchmark repo and tasks that compare agent output with and without JDAD | None | Phase 6 |
| **Distribution** | Claude marketplace (also read by Grok Build), Agent Plugins package for Codex and Cursor, versioning and update prompts | Claude plugin + marketplace | Phase 7 |
