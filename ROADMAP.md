# JDAD roadmap

Read [docs/VISION.md](docs/VISION.md) first. This file is the work queue for agents (Claude Code, Codex, Grok Build, Cursor) developing JDAD.

## How to use this file

1. Take the **first unchecked item** whose dependencies are checked and that isn't marked **Needs Jon** (or whose Jon input is already recorded on its card).
2. Find or create its Linear card (workspace `jongodb`, team `JON`, project `JDAD`) and post a plan there before writing code: steps, risks, and how each acceptance criterion will be verified.
3. Work on a branch, run `./verify`, and open a PR that links the card, shows evidence (commands and output), and lists anything unverified. Checker reviews it. Don't merge your own PR.
4. In the same PR, tick the item here (`- [x]`) and add the PR number after its title.

Each item is sized for one agent session. If an item turns out bigger, split it here first in its own small PR.

Legend: **Needs Jon** = needs a decision, access, or money from Jon before or during the item. IDs are stable; never renumber. Add new items at the end of a phase with the next free number.

---

## Phase 0: Foundation (done)

- [x] **P0.1 Knowledge base seed** (d104c73): `sources/` + `practices/performance.md` from the breakingbreach performance reel.
- [x] **P0.2 MCP server, HTTP transport, Claude Code plugin** (#1, JON-1330): `jdad-mcp` with 7 read-only tools, `kb://practices/{name}`, `apply-kb` prompt, bearer auth, host allowlist, `/jdad plan|review|perf|add`, `jdad-performance` skill, `./verify`, systemd deploy.
- [ ] **P0.3 Docker deploy to `jdad-mcp.jondevs.com`** (#2, in review): out of scope for this roadmap PR; tick when #2 merges.
- [x] **P0.4 Roadmap, vision, research, ADRs** (this PR).

## Phase 1: One source of truth

Goal: before adding features, make the repo itself cross-tool and give the KB and skills a schema that later phases build on.

- [ ] **P1.1 AGENTS.md becomes the canonical instructions file**
  - Goal: Codex, Cursor and Grok Build read the full repo rules, not just Claude Code. ([ADR 0004](docs/adr/0004-agents-md-canonical-instructions.md))
  - Deliverables: move the rules from `CLAUDE.md` into `AGENTS.md`; `CLAUDE.md` becomes `@AGENTS.md` plus Claude-only notes (plugin validate, `userConfig`); a test that enforces the sizes below.
  - Acceptance: `AGENTS.md` ≤ 150 lines and < 32 KiB; `CLAUDE.md` ≤ 40 lines and contains `@AGENTS.md`; no rule appears in both files; `./verify` passes; the PR shows `grok inspect` or `codex` output listing `AGENTS.md` if either CLI is available, otherwise lists it as unverified.
  - Depends on: #2 merged (both PRs edit `CLAUDE.md`).
- [ ] **P1.2 Practice schema and stable rule IDs**
  - Goal: every rule is addressable, so checklists, reviews and dedupe can cite `perf.db.n-plus-one` instead of a bullet's position.
  - Deliverables: `docs/kb-schema.md` (rule ID format, required tag, `src:` citation, optional `applies-when`, `origin: source|kb-addition`); migrate `practices/performance.md`; `jdad lint-kb` command (stdlib only) wired into `./verify`; `kb.py` parses IDs.
  - Acceptance: lint fails on a rule with no tag, no citation, a duplicate ID or an unknown tag (tests show each failure); all existing MCP tests pass; `search_practices` and `get_checklist` results include rule IDs.
  - Depends on: none.
- [ ] **P1.3 Source file schema and ingestion contract**
  - Goal: every source is a reproducible record that Daisy and other agents fill the same way.
  - Deliverables: YAML frontmatter for `sources/*.md` (`url`, `title`, `author`, `format`, `posted`, `retrieved`, `capture` = how the content was obtained, `items` = count of numbered practices); `sources/_TEMPLATE.md`; `jdad lint-kb` checks sources; migrate the existing source; a short "handoff contract" section in `docs/ingestion.md`.
  - Acceptance: lint fails on a missing field or a `src:` citation that points to a nonexistent source or item number; `list_sources` returns the new fields; existing tests pass.
  - Depends on: P1.2.
  - **Needs Jon:** how Daisy hands entries over (opens PRs into `JongoDB/jdad` herself, or sends a draft for another agent to commit).
- [ ] **P1.4 Canonical skills catalog**
  - Goal: one source for every skill, valid under the Agent Skills spec. ([ADR 0001](docs/adr/0001-canonical-skill-format-and-compilers.md))
  - Deliverables: `catalog/skills/<name>/SKILL.md` with spec-only frontmatter (`name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`) and tool extras under `metadata` (for example `metadata.claude.disable-model-invocation`); `catalog/rules/<name>.md` for always-on, glob-scoped rules; move `jdad-performance` in; a spec validator (name = directory, lowercase-hyphen, ≤64 chars, description ≤1024 chars, body < 500 lines) in `./verify`.
  - Acceptance: validator tests cover each spec rule with a failing fixture; `skills-ref validate` passes on every catalog skill if the tool installs offline, otherwise the PR says so; the plugin still installs (`claude plugin validate .` when the CLI is present).
  - Depends on: none.
- [ ] **P1.5 Skill compiler v0 (`jdad build`)**
  - Goal: generate each tool's files from the catalog so no one hand-edits four copies.
  - Deliverables: `jdad build` writing (a) plugin `skills/` for Claude Code (also read by Grok Build), (b) `dist/agents-skills/` for `.agents/skills/` (Codex, Cursor), (c) Cursor `.mdc` files from `catalog/rules/` (`description`, `globs`, `alwaysApply`); a generated-file header; `jdad build --check` in `./verify` fails when outputs are stale; golden-file tests per target.
  - Acceptance: changing a catalog skill without rebuilding fails `./verify`; golden tests pass; the generated Claude skill matches today's `skills/jdad-performance/SKILL.md` apart from the generated-file header (diff shown in the PR).
  - Depends on: P1.4.
- [ ] **P1.6 Dogfood the harness in this repo**
  - Goal: JDAD runs the same guardrails it will ship.
  - Deliverables: `.claude/settings.json` with deny rules (reading `.env*`, `**/*.pem`, `**/id_*`; `rm -rf`; `git push --force`) and a `Stop` hook that runs a fast verify subset (ruff + pytest -q) and exits 2 on failure; `LESSONS.md` seeded with the lessons from PR #1's six Checker rounds; a `./verify --fast` flag.
  - Acceptance: a test or recorded run shows the Stop hook blocking on a failing test; the deny rules parse (`claude` CLI validation if present, JSON schema check otherwise); `LESSONS.md` has at least 5 entries, each with a date and a link to the PR or verdict.
  - Depends on: P1.1 (so the hook command is documented in `AGENTS.md`).

## Phase 2: KB ingestion pipeline

Goal: video or article → source → practice, with dedupe, tags and citations, done the same way every time.

- [ ] **P2.1 Ingestion runbook and `jdad-ingest` skill**
  - Deliverables: `docs/ingestion.md` (capture → transcript → `sources/` record → fold into `practices/` → dedupe → version bump → PR); `catalog/skills/jdad-ingest/` for Daisy and other agents; `/jdad add` keeps routing to Daisy.
  - Acceptance: a dry run on one new article produces a source file and practice edits that pass `jdad lint-kb`; the runbook names the exact capture tool for video.
  - Depends on: P1.3, P1.5. **Needs Jon:** which video transcript tool Daisy uses and where raw transcripts may live (in repo or not).
- [ ] **P2.2 Duplicate and near-duplicate detection**
  - Deliverables: `jdad kb dupes` (offline token-overlap or TF-IDF similarity over rule text, stdlib only) listing candidate pairs above a threshold; a non-blocking report in `./verify` output.
  - Acceptance: tests with seeded duplicates and paraphrases catch them; no false positive on the current KB above the threshold.
  - Depends on: P1.2.
- [ ] **P2.3 Tag taxonomy v2**
  - Deliverables: add tags for `security`, `supply-chain`, `ci`, `process` (agent workflow), `design` (API and architecture), `ux`; document each in `docs/kb-schema.md`; `get_checklist` and the `/jdad` command accept them.
  - Acceptance: lint rejects unknown tags; MCP tests cover a new tag.
  - Depends on: P1.2. **Needs Jon:** approve the tag list.
- [ ] **P2.4 Ingest the harness research as KB sources**
  - Goal: the agent-workflow opinions in VISION.md become cited KB rules, not just prose.
  - Deliverables: `sources/` records for OpenAI "Harness engineering", Anthropic's long-running harness and harness-design posts, and Claude Code best practices (see `docs/research/`); `practices/agentic-workflow.md` tagged `[process]`; `catalog/skills/jdad-workflow/`.
  - Acceptance: every rule cites one of those sources or is labeled a KB addition; `get_checklist(["process"])` returns them.
  - Depends on: P1.3, P2.3.
- [ ] **P2.5 Citation integrity and source freshness**
  - Deliverables: lint that every `src:` resolves to a source and item; a report of sources older than 12 months whose topic has newer sources.
  - Acceptance: tests for a broken citation and a stale-source report.
  - Depends on: P1.3.

## Phase 3: MCP server v2

Goal: richer, still read-only and offline tools. ([ADR 0003](docs/adr/0003-stdio-plus-hosted-http-mcp.md))

- [ ] **P3.1 Ranked lexical search**
  - Deliverables: BM25 (stdlib) over rules; `search_practices(query, tags?, limit=10)` returns rule ID, topic, heading, snippet, score; a `concise|detailed` response format per Anthropic's tool-writing guidance.
  - Acceptance: tests with a fixture KB show expected top results for 10 queries; response size for `concise` stays under 2 KB for `limit=10`.
  - Depends on: P1.2.
- [ ] **P3.2 Optional semantic search**
  - Deliverables: `jdad[semantic]` extra with a small local embedding model; index built at deploy or update time, not per request; `search_practices(mode="semantic")` falls back to lexical when the extra isn't installed.
  - Acceptance: server starts and passes all tests without the extra; with it, a paraphrase test set beats lexical recall@5; droplet memory use measured and recorded in the PR.
  - Depends on: P3.1. **Needs Jon:** OK to add the dependency and the RAM on the droplet.
- [ ] **P3.3 Checklists v2**
  - Deliverables: `get_checklist(tags, phase="plan|review|ship")` returns Markdown checkboxes with rule IDs and citations; `kb://checklists/{tag}` resources.
  - Acceptance: tests for each phase; `/jdad plan` and `/jdad review` use rule IDs.
  - Depends on: P1.2.
- [ ] **P3.4 `review_against_kb` tool and prompt**
  - Deliverables: `review_against_kb(changed_files: list[str], summary: str, tags?: list[str])` returns the applicable rules (inferred from file types and tags), a review rubric (correctness first, "skip style"), and a required findings format (rule ID, file, evidence, severity). The server does no model calls; the calling agent does the review. A matching `review-against-kb` prompt.
  - Acceptance: tests show tag inference for frontend, backend, db and infra file sets; output contains only rules whose tags match; `/jdad review` uses it.
  - Depends on: P3.3.
- [ ] **P3.5 Templates as resources and `bootstrap_repo`**
  - Deliverables: `kb://templates/{path}` resources for every harness template; `bootstrap_repo(tools, stack)` returns a manifest of `{path, content, mode}` for the client to write. The server writes nothing.
  - Acceptance: tests show the manifest matches `jdad init --dry-run` output for the same inputs; no filesystem writes (existing no-write test extended).
  - Depends on: P4.3.
- [ ] **P3.6 MCP spec 2026-07-28 readiness and tool evals**
  - Deliverables: track the Python SDK's support for the stateless revision (`server/discover`, no `initialize`); upgrade when released; a 10-task tool-use eval (agent asked KB questions; graded on correct tool and rule ID).
  - Acceptance: compatibility notes in `docs/research/open-standards.md` updated; eval results committed under `docs/evals/`.
  - Depends on: P3.1.
- [ ] **P3.7 Token UX via plugin `userConfig`**
  - Deliverables: Claude plugin `userConfig.jdad_token` with `sensitive: true`, used in the MCP header; README update; env-var path kept as fallback.
  - Acceptance: `claude plugin validate .` passes; a live connection to a local server with the prompted token shown in the PR (or listed as unverified).
  - Depends on: #2 merged.

## Phase 4: Harness templates and `jdad init`

Goal: drop the JDAD harness into any repo in one command, and keep it current.

- [ ] **P4.1 Template set v1 (instructions and docs)**
  - Deliverables: `templates/harness/` with `AGENTS.md` (~100-line map), `CLAUDE.md` (`@AGENTS.md` + Claude notes), `DESIGN.md` (requirements with acceptance criteria, design, risks), `PLAN.md` (steps, sprint contract: done criteria and how each is verified), `VERIFY.md` (the verify contract), `LESSONS.md`, `docs/adr/0000-template.md`, `docs/exec-plans/{active,completed}/`.
  - Acceptance: a test renders the templates with sample values and checks size limits (AGENTS.md ≤ 120 lines) and required headings; no placeholder left unrendered.
  - Depends on: P1.1.
- [ ] **P4.2 Tool configs per harness**
  - Deliverables: `.claude/settings.json` (deny rules, Stop hook → `./verify --fast`), `.mcp.json`; `.codex/config.toml` (`sandbox_mode = "workspace-write"`, `approval_policy = "on-request"`, `[mcp_servers.jdad]` with `bearer_token_env_var`); `.grok/config.toml` (`[mcp_servers.jdad]` with `${JDAD_TOKEN}` header, `[permission]` deny rules); `.cursor/mcp.json`; Cursor `.mdc` rules from the compiler.
  - Acceptance: every file parses (JSON/TOML) in tests; where the CLI is installed, `claude plugin validate`, `grok inspect --json` and `agent mcp list` output is attached; otherwise listed as unverified.
  - Depends on: P4.1, P1.5.
- [ ] **P4.3 `jdad init`**
  - Deliverables: `jdad init [--tools claude,codex,cursor,grok] [--stack python|node|go] [--dry-run] [--force]`, runnable with `uvx`; idempotent; never overwrites without `--force`; writes `.jdad/manifest.json` (template version and file hashes).
  - Acceptance: tests in temp dirs: fresh init, rerun (no changes), existing `AGENTS.md` preserved without `--force`, `--dry-run` writes nothing.
  - Depends on: P4.2.
- [ ] **P4.4 `jdad sync` and `jdad doctor`**
  - Deliverables: `sync` updates untouched template files and shows a diff for edited ones (using manifest hashes); `doctor` checks harness health (instructions size, `./verify` exists and is executable, hooks parse, MCP config present, no secrets in tracked config).
  - Acceptance: tests for each doctor check and for sync on edited vs untouched files.
  - Depends on: P4.3.
- [ ] **P4.5 Stack-specific `./verify` scaffolds**
  - Deliverables: `./verify` templates for Python (uv, ruff, pytest), Node/TypeScript (pnpm, eslint, tsc, vitest) and Go (gofmt, vet, test), each with `--fast`.
  - Acceptance: each scaffold passes in a tiny fixture project in CI.
  - Depends on: P4.3, P5.1. **Needs Jon:** which stacks first.

## Phase 5: Production defaults

Goal: the verify/CI, security, observability and performance opinions as KB rules, skills and template pieces. Rules need cited sources; anything without one is labeled a KB addition.

- [ ] **P5.1 Verify and CI standard**
  - Deliverables: `practices/verify-ci.md`; `VERIFY.md` contract (stages: format, lint, typecheck, unit, integration, build, secret scan, dependency audit; exit codes; `--fast`); GitHub Actions template with SHA-pinned actions, `permissions: contents: read`, concurrency groups; a branch-protection checklist.
  - Acceptance: the template workflow passes `actionlint` in tests; this repo's own workflow conforms.
  - Depends on: P2.3. **Needs Jon:** GitHub Actions billing (CI runs were blocked on JDAD PR #1).
- [ ] **P5.2 Security and supply-chain defaults**
  - Deliverables: `practices/security.md` and `practices/supply-chain.md` (secret scanning with gitleaks in pre-commit and CI, Dependabot or Renovate, OSV-Scanner, pinned actions and lockfiles, optional SBOM, OpenSSF Scorecard; agent-specific: deny reading secret files, review project hooks and MCP servers before trust, pin marketplace sources by SHA, hooks fail open in Grok Build so CI stays the backstop); template pieces.
  - Acceptance: each rule cited or labeled; templates include gitleaks config and a Dependabot file that parse in tests.
  - Depends on: P2.3, P4.2.
- [ ] **P5.3 Security review skills**
  - Deliverables: `catalog/skills/jdad-security-review/` that runs the KB checklist and recommends Trail of Bits' `differential-review`, `insecure-defaults` and `supply-chain-risk-auditor`; optional CI job using `anthropics/claude-code-security-review`. Any third-party skill or action gets a recorded review before a template recommends it.
  - Acceptance: skill passes the validator; the CI job is opt-in and documented; the review notes for each recommended third-party item are linked.
  - Depends on: P5.2.
- [ ] **P5.4 Observability defaults**
  - Deliverables: `practices/observability.md` (OpenTelemetry traces, structured JSON logs with request IDs, `/healthz` and `/readyz`, RED metrics, error tracking, local logs an agent can query); per-stack snippets in templates.
  - Acceptance: rules cited or labeled; the Python snippet runs in a fixture test and emits a span to an in-memory exporter.
  - Depends on: P2.3.
- [ ] **P5.5 Performance budgets**
  - Deliverables: extend `practices/performance.md` with budget rules (bundle size, Lighthouse CI thresholds, p95 latency targets) and optional verify stages.
  - Acceptance: budgets are configurable per repo; rules cited or labeled.
  - Depends on: P5.1.
- [ ] **P5.6 Edge protection for the hosted MCP endpoint**
  - Deliverables: rate limiting and WAF rules (Cloudflare) or an app-level limiter for `jdad-mcp.jondevs.com`; a token-rotation runbook; this carries forward PR #2's "not in this release" note.
  - Acceptance: a burst test from outside shows throttling; the rotation runbook has been run once on a test token.
  - Depends on: #2 merged. **Needs Jon:** Cloudflare dashboard changes.

## Phase 6: Evals

Goal: prove the opinions improve agent output, and catch regressions when the KB, skills or models change.

- [ ] **P6.1 Eval design and benchmark repo skeleton**
  - Deliverables: `docs/evals/DESIGN.md`; a separate `JongoDB/jdad-bench` repo with 6–10 small tasks (for example: a paginated list endpoint with an N+1 trap, an outbound call that needs a timeout, a feature that needs tests, a bug fix, adding tracing, a config with a secret-handling trap), each with hidden tests and a task prompt.
  - Acceptance: every task has a failing hidden test on the starting commit and a reference solution that passes.
  - Depends on: P3.3. **Needs Jon:** create the repo (private?) and approve the task list.
- [ ] **P6.2 Headless runner**
  - Deliverables: a runner that executes each task with and without JDAD (harness + MCP) across `claude -p --bare`, `codex exec`, `grok -p --output-format json --no-auto-update` and `agent -p`; N runs per cell; per-run turn and budget caps; JSON results.
  - Acceptance: a dry run with one task and one tool produces a results file; caps are enforced.
  - Depends on: P6.1, P4.3. **Needs Jon:** API keys and a monthly eval budget.
- [ ] **P6.3 Graders**
  - Deliverables: hidden tests pass; `./verify` passes; KB-rule detectors (static checks such as pagination present or timeouts set); an LLM judge with a rubric run as a separate reviewer.
  - Acceptance: each grader has unit tests on known-good and known-bad outputs.
  - Depends on: P6.1.
- [ ] **P6.4 Skill-trigger evals**
  - Deliverables: `evals/` suite for the Claude plugin run with `claude plugin eval`, including a no-plugin baseline; CI gate threshold.
  - Acceptance: suite runs locally with results committed; threshold documented.
  - Depends on: P1.5.
- [ ] **P6.5 First eval report**
  - Deliverables: `docs/evals/REPORT-<date>.md` comparing baseline vs JDAD per tool and task, with cost.
  - Acceptance: every opinion that showed no gain is listed with a keep, revise or drop decision.
  - Depends on: P6.2, P6.3.

## Phase 7: Distribution, versioning and update prompts

- [ ] **P7.1 Versioning and release policy**
  - Deliverables: ADR for semver of the plugin and package, with KB identity as git SHA + newest entry date (already in `kb_version`); `CHANGELOG.md`; a tag-triggered release workflow.
  - Acceptance: a test release on a branch produces a GitHub release with notes; version lockstep check still passes.
  - Depends on: P5.1.
- [ ] **P7.2 Update prompts**
  - Deliverables: install docs that turn on marketplace auto-update (off by default for third-party Claude marketplaces); `/jdad` compares the plugin version with the server's `kb_version` and tells the user when the plugin is behind; optional `SessionStart` hook that prints one line when an update exists.
  - Acceptance: test with a stubbed older plugin version shows the notice; no network call from the server.
  - Depends on: P7.1. **Needs Jon:** OK to enable auto-update on his hosts.
- [ ] **P7.3 Codex and Cursor package (Agent Plugins)**
  - Deliverables: compiler emits an Agent Plugins package (root `plugin.json`, `skills/`, `mcp.json`) and `.agents/plugins/marketplace.json`; install docs for Codex and Cursor.
  - Acceptance: package validates against the Agent Plugins JSON schema; where the CLIs are installed, `codex` and `agent mcp list` show JDAD; otherwise unverified.
  - Depends on: P1.5.
- [ ] **P7.4 Grok Build install proof**
  - Deliverables: install the existing Claude marketplace with `grok plugin marketplace add`, capture `grok inspect --json`; add a `.grok-plugin/marketplace.json` only if the Claude one doesn't load.
  - Acceptance: `grok inspect --json` output in the PR shows the JDAD skills and MCP server.
  - Depends on: #2 merged. **Needs Jon:** a host with Grok Build installed and logged in.
- [ ] **P7.5 Install matrix and smoke scripts**
  - Deliverables: `docs/install.md` table (tool × install command × token setup × verify command); `scripts/smoke-<tool>.sh` that checks the MCP connection.
  - Acceptance: smoke scripts run green on at least one host per tool, or the gap is listed.
  - Depends on: P7.3, P7.4.

## Phase 8: Docs site and gardening (optional)

- [ ] **P8.1 Docs site**
  - Deliverables: a static site from `docs/`, `practices/` and `ROADMAP.md`, deployed on Cloudflare Pages.
  - Acceptance: builds in CI; links checked.
  - Depends on: P5.1. **Needs Jon:** public or private (behind Cloudflare Access).
- [ ] **P8.2 Doc-gardening routine**
  - Deliverables: a scheduled agent that checks links, research files older than 90 days, roadmap items with merged PRs but unticked boxes, and opens a fix-up PR.
  - Acceptance: one recorded run with a PR.
  - Depends on: P2.5.
- [ ] **P8.3 KB stats**
  - Deliverables: `kb://stats` resource (rules per tag and topic, sources count, newest entry).
  - Acceptance: MCP test.
  - Depends on: P1.2.
