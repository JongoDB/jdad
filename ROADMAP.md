# JDAD roadmap

Read [docs/VISION.md](docs/VISION.md) first. This file is the work queue for agents (Claude Code, Codex, Grok Build, Cursor) developing JDAD.

## How to use this file

1. Take the **first unchecked item** whose dependencies are checked and that isn't marked **Needs Jon** (or whose Jon input is already recorded on its card or as a **Decision** line here).
2. Find or create its Linear card (workspace `jongodb`, team `JON`, project `JDAD`) and post a plan there before writing code: steps, risks, and how each acceptance criterion will be verified.
3. Work on a branch, run `./verify`, and open a PR that links the card, shows evidence (commands and output), and lists anything unverified. Checker reviews it. Don't merge your own PR.
4. In the same PR, tick the item here (`- [x]`) and add the PR number after its title.

Acceptance criteria are pass/fail. The part of a criterion after "Runtime:" needs a real CLI, host or service; if that isn't available, record "runtime unverified" on the card and leave the box unchecked. Listing something as unverified is disclosure, not a pass.

Each item is sized for one agent session. If an item turns out bigger, split it here first in its own small PR.

Legend: **Needs Jon** = needs a decision, access, or money from Jon before or during the item. IDs are stable; never renumber. Add new items at the end of a phase with the next free number.

---

## Phase 0: Foundation (done)

- [x] **P0.1 Knowledge base seed** (d104c73): `sources/` + `practices/performance.md` from the breakingbreach performance reel.
- [x] **P0.2 MCP server, HTTP transport, Claude Code plugin** (#1, JON-1330): `jdad-mcp` with 7 read-only tools, `kb://practices/{name}`, `apply-kb` prompt, bearer auth, host allowlist, `/jdad plan|review|perf|add`, `jdad-performance` skill, `./verify`, systemd deploy.
- [x] **P0.3 Docker deploy merged** (#2, 2022a8a). Acceptance: #2 is merged to `main` (merge commit 2022a8a), and the full `./verify`, including `tests/test_docker.sh`, passes on this roadmap PR's head after it merges `main`. Merging doesn't mean deployed; that is P0.5.
- [x] **P0.4 Roadmap, vision, research, ADRs** (this PR).
- [ ] **P0.5 Hosted endpoint deployed and proven** ([ADR 0005](docs/adr/0005-hosted-deploy-cloudflare-full-strict.md))
  - Acceptance: on the droplet, the running container's `JDAD_GIT_SHA` equals `main`'s head SHA; through `https://jdad-mcp.jondevs.com/mcp` with a valid token, `initialize`, `tools/list` and one `tools/call` return 200; with no token, 401; a request with a non-allowlisted `Host` gets 421 at the origin; `curl` with the Cloudflare Origin CA root as `--cacert` verifies the origin certificate; Cloudflare's SSL mode for the host is Full (strict). Tokens redacted in the PR. When this passes, ADR 0005 moves to Accepted.
  - Depends on: P0.3. **Needs Jon:** droplet access and the Cloudflare Configuration Rule.

## Phase 1: One source of truth

Goal: before adding features, make the repo itself cross-tool and give the KB and skills a schema that later phases build on.

- [ ] **P1.1 AGENTS.md becomes the canonical instructions file**
  - Goal: Codex, Cursor and Grok Build read the full repo rules, not just Claude Code. ([ADR 0004](docs/adr/0004-agents-md-canonical-instructions.md))
  - Deliverables: move the rules from `CLAUDE.md` into `AGENTS.md`; `CLAUDE.md` becomes `@AGENTS.md` plus Claude-only notes (plugin validate, `userConfig`); a test that enforces the sizes below.
  - Acceptance: `AGENTS.md` ≤ 120 lines and < 32 KiB; `CLAUDE.md` ≤ 40 lines and contains `@AGENTS.md`; every normative rule has an ID (`R-<area>-<n>`) listed in a table in `AGENTS.md`, and a test asserts each ID appears in exactly one of `AGENTS.md` or `CLAUDE.md`'s "Claude-only" section; `./verify` passes. Runtime: on one installed CLI, a discovery run lists `AGENTS.md`: either `grok inspect --json` output names it, or `codex -c log_dir=./.codex-log --ask-for-approval never "Show which instruction files are active."` run from the repo root leaves `./.codex-log/codex-tui.log` containing `AGENTS.md` (the audit method in Codex's AGENTS.md guide); without it the item stays open as runtime unverified.
  - Depends on: P0.3 (done; both PRs edit `CLAUDE.md`).
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
  - Prerequisite (before any bot opens KB PRs): branch protection on `main`: a pull request is required before merging (no direct pushes), force pushes and branch deletion are blocked, and the rule applies to admins; the `verify` status check becomes required once GitHub Actions runs again (P5.1). Required approvals wait until reviewers use a separate GitHub account, because today every bot acts as `JongoDB` and a required approval would block every merge. Evidence: `gh api repos/JongoDB/jdad/branches/main/protection` output in the PR. This is a GitHub settings change, not a repo change. **Needs Jon:** apply the branch protection (repo admin). Until then, "nobody merges their own PR" is policy only.
  - Decision (Jon, 2026-11-22 11:35 AM ET): bots, Daisy included, may open KB PRs into `JongoDB/jdad` themselves. The handoff contract assumes that; Checker still reviews and nobody merges their own PR.
- [ ] **P1.4 Canonical skills catalog**
  - Goal: one source for every skill, valid under the Agent Skills spec. ([ADR 0001](docs/adr/0001-canonical-skill-format-and-compilers.md))
  - Deliverables: `catalog/skills/<name>/SKILL.md` with spec-only frontmatter (`name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`) and tool extras under `metadata` (for example `metadata.claude.disable-model-invocation`); `catalog/rules/<name>.md` for always-on, glob-scoped rules; move `jdad-performance` in; a spec validator (name = directory, lowercase-hyphen, ≤64 chars, description ≤1024 chars, body < 500 lines) in `./verify`.
  - Acceptance: validator tests have one failing fixture per spec rule listed in the deliverables (name = directory, charset, ≤64 chars, description ≤1024 chars, body < 500 lines, unknown top-level frontmatter key); `skills-ref validate` at a pinned version (recorded in the PR) exits 0 on every catalog skill; `claude plugin validate .` exits 0. Runtime: in a temp `HOME`, `claude plugin marketplace add` + `claude plugin install` succeed and the installed manifest lists the catalog skills; without a CLI the item stays open as runtime unverified.
  - Depends on: none.
- [ ] **P1.5 Skill compiler v0 (`jdad build`)**
  - Goal: generate each tool's files from the catalog so no one hand-edits four copies.
  - Deliverables: `jdad build` writing (a) plugin `skills/` for Claude Code (also read by Grok Build), (b) `dist/agents-skills/` for `.agents/skills/` (Codex, Cursor), (c) Cursor `.mdc` files from `catalog/rules/` (`description`, `globs`, `alwaysApply`); a generated-file header; `jdad build --check` in `./verify` fails when outputs are stale; golden-file tests per target.
  - Acceptance: changing a catalog skill without rebuilding fails `./verify`; golden tests pass; the generated Claude skill matches today's `skills/jdad-performance/SKILL.md` apart from the generated-file header (diff shown in the PR).
  - Depends on: P1.4.
- [ ] **P1.6 Dogfood the harness in this repo**
  - Goal: JDAD runs the same guardrails it will ship.
  - Deliverables: `.claude/settings.json` with deny rules (reading `.env*`, `**/*.pem`, `**/id_*`; `rm -rf`; `git push --force`) and a `Stop` hook that runs a fast verify subset (ruff + pytest -q) and exits 2 on failure; `LESSONS.md` seeded with the lessons from PR #1's six Checker rounds; a `./verify --fast` flag.
  - Acceptance: tests drive the hook and permission fixtures: an allowed read succeeds; reads of `.env`, `x.pem` and `id_ed25519` and the `rm -rf` and `git push --force` fixtures each return deny before execution; a failing pytest fixture makes the Stop hook exit 2 and a passing one exits 0; `./verify --fast` runs ruff and pytest and exits non-zero when either fails; `LESSONS.md` has at least 5 entries, each with a date and a link to the PR or verdict.
  - Depends on: P1.1 (so the hook command is documented in `AGENTS.md`).

## Phase 2: KB ingestion pipeline

Goal: video or article → source → practice, with dedupe, tags and citations, done the same way every time.

- [ ] **P2.1 Ingestion runbook and `jdad-ingest` skill**
  - Deliverables: `docs/ingestion.md` (capture → transcript → `sources/` record → fold into `practices/` → dedupe → version bump → PR); `catalog/skills/jdad-ingest/` for Daisy and other agents; `/jdad add` keeps routing to Daisy.
  - Acceptance: a dry run on one new article produces a source file and practice edits that pass `jdad lint-kb`; the runbook names the exact capture tool for video.
  - Depends on: P1.3, P1.5. **Needs Jon:** which video transcript tool Daisy uses and where raw transcripts may live (in repo or not).
- [ ] **P2.2 Duplicate and near-duplicate detection**
  - Deliverables: `jdad kb dupes` (offline token-overlap or TF-IDF similarity over rule text, stdlib only) listing candidate pairs above a threshold; a non-blocking report in `./verify` output.
  - Acceptance: a committed fixture file labels pairs as duplicate, paraphrase or distinct, and the PR records the cutoff θ; at θ, every exact-duplicate pair is reported, paraphrase recall ≥ 0.8, and no pair in the current KB labeled distinct is reported; the score output is in the PR.
  - Depends on: P1.2.
- [ ] **P2.3 Tag taxonomy v2**
  - Deliverables: add tags for `security`, `supply-chain`, `ci`, `process` (agent workflow), `design` (API and architecture), `ux`; document each in `docs/kb-schema.md`; `get_checklist` and the `/jdad` command accept them.
  - Acceptance: lint and `get_checklist` tests are parametrized over all six new tags; each tag returns its seeded rule ID and excludes rules with other tags; an unknown tag fails lint with the tag name in the error.
  - Depends on: P1.2. **Needs Jon:** approve the tag list.
- [ ] **P2.4 Ingest the harness research as KB sources**
  - Goal: the agent-workflow opinions in VISION.md become cited KB rules, not just prose.
  - Deliverables: `sources/` records for OpenAI "Harness engineering", Anthropic's long-running harness and harness-design posts, and Claude Code best practices (see `docs/research/`); `practices/agentic-workflow.md` tagged `[process]`; `catalog/skills/jdad-workflow/`.
  - Acceptance: every rule cites one of those sources or is labeled a KB addition; `get_checklist(["process"])` returns them.
  - Depends on: P1.3, P2.3.
- [ ] **P2.5 Citation integrity and source freshness**
  - Deliverables: lint that every `src:` resolves to a source and item; a report of sources older than 12 months whose topic has newer sources.
  - Acceptance: with the date frozen in tests: source A older than 365 days plus a same-topic source B newer than A produces an A→B line in the report; a source with no newer same-topic peer isn't reported; a `src:` to a missing source or item number makes lint exit non-zero and names the citation.
  - Depends on: P1.3.

## Phase 3: MCP server v2

Goal: richer, still read-only and offline tools. ([ADR 0003](docs/adr/0003-stdio-plus-hosted-http-mcp.md))

- [x] **P3.1 Ranked lexical search**
  - Deliverables: BM25 (stdlib) over rules; `search_practices(query, tags?, limit=10)` returns rule ID, topic, heading, snippet, score; a `concise|detailed` response format per Anthropic's tool-writing guidance.
  - Acceptance: a fixture KB and expected top-3 rule IDs for 10 queries are committed; tests assert those IDs in order; with `limit=10` and `concise`, the UTF-8 response is ≤ 2048 bytes.
  - Depends on: P1.2.
  - Evidence (2026-11-22, JON-1346): `tests/fixtures/search/` (21 rules) and `queries.json` (10 queries, expected top-3 IDs in order); `tests/test_search.py` asserts them; with `limit=10` and `concise`, the UTF-8 JSON response is within 2048 bytes on the fixture and on the repo KB.
- [ ] **P3.2 Optional semantic search**
  - Deliverables: `jdad[semantic]` extra with a small local embedding model; index built at deploy or update time, not per request; `search_practices(mode="semantic")` falls back to lexical when the extra isn't installed.
  - Acceptance: server starts and the full suite passes without the extra; with it, on ≥ 20 committed, labeled paraphrase queries, semantic recall@5 ≥ lexical recall@5 + 0.10; peak RSS under a fixed 100-request workload is recorded in the PR and is ≤ the memory budget Jon approves on the card.
  - Depends on: P3.1. **Needs Jon:** the droplet's new RAM size and the memory budget for the acceptance check. Both stay open until Jon regains DigitalOcean console access (support ticket open).
  - Decision (Jon, 2026-11-22 11:35 AM ET): semantic search and its dependency are approved, and the droplet's RAM will be increased.
- [ ] **P3.3 Checklists v2**
  - Deliverables: `get_checklist(tags, phase="plan|review|ship")` returns Markdown checkboxes with rule IDs and citations; `kb://checklists/{tag}` resources.
  - Acceptance: for each of `plan`, `review` and `ship`, tests assert the rule IDs selected for a fixture tag set, that every line matches `- [ ] <rule-id>: <text> (<citation URL>)`, and that `kb://checklists/{tag}` equals `get_checklist([tag])`; tests on the command files assert `/jdad plan` and `/jdad review` instruct the agent to cite rule IDs.
  - Depends on: P1.2.
- [ ] **P3.4 `review_against_kb` tool and prompt**
  - Deliverables: `review_against_kb(changed_files: list[str], summary: str, tags?: list[str])` returns the applicable rules (inferred from file types and tags), a review rubric (correctness first, "skip style"), and a required findings format (rule ID, file, evidence, severity). The server does no model calls; the calling agent does the review. A matching `review-against-kb` prompt.
  - Acceptance: tests show tag inference for frontend, backend, db and infra file sets; output contains only rules whose tags match; a test on `commands/jdad.md` asserts the `review` section tells the agent to call `review_against_kb` and to report findings in its rule-ID / file / evidence / severity format.
  - Depends on: P3.3.
- [ ] **P3.5 Templates as resources and `bootstrap_repo`**
  - Deliverables: `kb://templates/{path}` resources for every harness template; `bootstrap_repo(tools, stack)` returns a manifest of `{path, content, mode}` for the client to write. The server writes nothing.
  - Acceptance: for each `tools × stack` fixture, tests assert the `bootstrap_repo` manifest equals `jdad init --dry-run` output; a new test snapshots the repo and temp dirs (paths, sizes, mtimes) before and after `bootstrap_repo` and asserts no change. (Today's tests check read-only tool annotations and path traversal, not filesystem writes, so this test is new.)
  - Depends on: P4.3.
- [ ] **P3.6 MCP spec 2026-07-28 readiness and tool evals**
  - Deliverables: track the Python SDK's support for the stateless revision (`server/discover`, no `initialize`); upgrade when released; a 10-task tool-use eval (agent asked KB questions; graded on correct tool and rule ID).
  - Acceptance: `docs/research/open-standards.md` has a matrix row per pinned SDK version with pass/fail for `initialize` and `server/discover`; the server doesn't switch protocol revisions while any target client row fails; 10 labeled KB tasks are committed, and the eval shows ≥ 9 correct tool choices and ≥ 9 correct rule IDs.
  - Depends on: P3.1.
- [ ] **P3.7 Token UX via plugin `userConfig`**
  - Deliverables: Claude plugin `userConfig.jdad_token` with `sensitive: true`, used in the MCP header; README update; env-var path kept as fallback.
  - Acceptance: `claude plugin validate .` exits 0. Runtime: with an ephemeral, local-only test token (generated for the run, never a real JDAD token), a local server shows 200 for the prompted token and 401 for a missing or wrong token; the PR shows a transcript with the token redacted; `grep` for the token value over server logs and the PR body finds nothing; the test token is then destroyed. Without a Claude CLI the item stays open as runtime unverified.
  - Depends on: P0.3.

## Phase 4: Harness templates and `jdad init`

Goal: drop the JDAD harness into any repo in one command, and keep it current.

- [ ] **P4.1 Template set v1 (instructions and docs)**
  - Deliverables: `templates/harness/` with `AGENTS.md` (map, ≤ 120 lines), `CLAUDE.md` (`@AGENTS.md` + Claude notes), `DESIGN.md` (requirements with acceptance criteria, design, risks), `PLAN.md` (steps, sprint contract: done criteria and how each is verified), `VERIFY.md` (the verify contract), `LESSONS.md`, `docs/adr/0000-template.md`, `docs/exec-plans/{active,completed}/`.
  - Acceptance: a schema file lists the required headings for each of the 7 templates and a test asserts the exact set; rendering a committed fixture gives `AGENTS.md` ≤ 120 lines and zero unrendered `{{…}}` placeholders.
  - Depends on: P1.1.
- [ ] **P4.2 Tool configs per harness**
  - Deliverables: `.claude/settings.json` (deny rules, Stop hook → `./verify --fast`), `.mcp.json`; `.codex/config.toml` (`sandbox_mode = "workspace-write"`, `approval_policy = "on-request"`, `[mcp_servers.jdad]` with `bearer_token_env_var`); `.grok/config.toml` (`[mcp_servers.jdad]` with `${JDAD_TOKEN}` header, `[permission]` deny rules); `.cursor/mcp.json`; Cursor `.mdc` rules from the compiler.
  - Acceptance: every file parses (JSON/TOML) in tests; a test asserts each config denies `.env*` reads and sets the JDAD MCP entry with the token taken from the environment, not a literal. Runtime, per tool with an installed CLI: against a local test server, a denied read is refused and an MCP call with the env-var token succeeds, with `claude plugin validate`, `grok inspect --json` or `agent mcp list` output attached. Tools without a CLI stay open as runtime unverified in a checklist on the card.
  - Depends on: P4.1, P1.5.
- [ ] **P4.3 `jdad init`**
  - Deliverables: `jdad init [--tools claude,codex,cursor,grok] [--stack python|node|go] [--dry-run] [--force]`, runnable with `uvx`; idempotent; never overwrites without `--force`; writes `.jdad/manifest.json` (template version and file hashes).
  - Acceptance: tests in temp dirs: fresh init, rerun (no changes), existing `AGENTS.md` preserved without `--force`, `--dry-run` writes nothing.
  - Depends on: P4.2.
- [ ] **P4.4 `jdad sync` and `jdad doctor`**
  - Deliverables: `sync` updates untouched template files and shows a diff for edited ones (using manifest hashes); `doctor` checks harness health (instructions size, `./verify` exists and is executable, hooks parse, MCP config present, no secrets in tracked config).
  - Acceptance: each doctor check has a passing and a failing fixture with exit codes 0 and 1; `sync` updates an untouched file and leaves an edited file byte-identical while printing its diff.
  - Depends on: P4.3.
- [ ] **P4.5 Stack-specific `./verify` scaffolds**
  - Deliverables: `./verify` templates for Python (uv, ruff, pytest), Node/TypeScript (pnpm, eslint, tsc, vitest) and Go (gofmt, vet, test), each with `--fast`.
  - Acceptance: each scaffold passes in a tiny fixture project in CI.
  - Depends on: P4.3, P5.1. **Needs Jon:** which stacks first.

## Phase 5: Production defaults

Goal: the verify/CI, security, observability and performance opinions as KB rules, skills and template pieces. Rules need cited sources; anything without one is labeled a KB addition.

- [ ] **P5.1 Verify and CI standard**
  - Deliverables: `practices/verify-ci.md`; `VERIFY.md` contract (stages: format, lint, typecheck, unit, integration, build, secret scan, dependency audit; exit codes; `--fast`); GitHub Actions template with SHA-pinned actions, `permissions: contents: read`, concurrency groups; a branch-protection checklist.
  - Acceptance: `actionlint` exits 0 on the template workflow and this repo's workflow; a test checks both against a machine-readable schema of the contract: required stages present, every `uses:` pinned to a 40-character SHA, `permissions: contents: read`, a `concurrency` group, and `--fast` running only the format, lint and unit stages.
  - Depends on: P2.3.
  - Decision (Jon, 2026-11-22 11:35 AM ET): fixing GitHub Actions billing is approved (CI runs were blocked on JDAD PR #1). Until a run shows on a PR, CI evidence comes from local `./verify`.
- [ ] **P5.2 Security and supply-chain defaults**
  - Deliverables: `practices/security.md` and `practices/supply-chain.md` (secret scanning with gitleaks in pre-commit and CI, Dependabot or Renovate, OSV-Scanner, pinned actions and lockfiles, optional SBOM, OpenSSF Scorecard; agent-specific: deny reading secret files, review project hooks and MCP servers before trust, pin marketplace sources by SHA, hooks fail open in Grok Build so CI stays the backstop); template pieces.
  - Acceptance: each rule cited or labeled; with the template gitleaks config, a fake-secret fixture makes gitleaks exit 1 and a clean fixture exits 0; the Dependabot file validates against its schema; OSV-Scanner exits non-zero on a lockfile fixture with a known vulnerable version.
  - Depends on: P2.3, P4.2.
- [ ] **P5.3 Security review skills**
  - Deliverables: `catalog/skills/jdad-security-review/` that runs the KB checklist and recommends Trail of Bits' `differential-review`, `insecure-defaults` and `supply-chain-risk-auditor`; optional CI job using `anthropics/claude-code-security-review`. Any third-party skill or action gets a recorded review before a template recommends it.
  - Acceptance: skill passes the validator; the CI job runs only when the repo variable `JDAD_SECURITY_REVIEW` is `true` (a test on the workflow template asserts the job's `if:` checks it, and `actionlint` passes); `catalog/skills/jdad-security-review/SKILL.md` has an "Enable the CI job" section naming that variable and the API-key secret the action needs; the review notes for each recommended third-party item are linked.
  - Depends on: P5.2.
- [ ] **P5.4 Observability defaults**
  - Deliverables: `practices/observability.md` (OpenTelemetry traces, structured JSON logs with request IDs, `/healthz` and `/readyz`, RED metrics, error tracking, local logs an agent can query); per-stack snippets in templates.
  - Acceptance: rules cited or labeled; the Python snippet runs in a fixture test and emits a span to an in-memory exporter.
  - Depends on: P2.3.
- [ ] **P5.5 Performance budgets**
  - Deliverables: extend `practices/performance.md` with budget rules (bundle size, Lighthouse CI thresholds, p95 latency targets) and optional verify stages.
  - Acceptance: a fixture config sets limits for bundle bytes, a Lighthouse score and p95 latency; for each, a below-limit fixture passes and an above-limit fixture fails with measured vs target in the output; overriding the limit in the repo config flips the result; rules cited or labeled.
  - Depends on: P5.1.
- [ ] **P5.6 Edge protection for the hosted MCP endpoint**
  - Deliverables: rate limiting and WAF rules (Cloudflare) or an app-level limiter for `jdad-mcp.jondevs.com`; a token-rotation runbook. PR #2's Unverified list defers this: "Rate limiting / WAF is deferred for this release (already covered as P5.6 in the roadmap PR)."
  - Acceptance: with a test token and a test hostname or a staging rule (no flood against production): after N requests in the configured window the endpoint returns 429 with `Retry-After`, and returns 200 again after the window; N and the window are in the runbook. Rotation: after following the runbook once, the old token gets 401 and the new token gets 200; tokens are redacted in the PR.
  - Depends on: P0.5. **Needs Jon:** Cloudflare dashboard changes.

## Phase 6: Evals

Goal: prove the opinions improve agent output, and catch regressions when the KB, skills or models change.

- [ ] **P6.1 Eval design and benchmark repo skeleton**
  - Deliverables: `docs/evals/DESIGN.md`; a separate `JongoDB/jdad-bench` repo with 6–10 small tasks (for example: a paginated list endpoint with an N+1 trap, an outbound call that needs a timeout, a feature that needs tests, a bug fix, adding tracing, a config with a secret-handling trap), each with hidden tests and a task prompt.
  - Acceptance: every task has a failing hidden test on the starting commit and a reference solution that passes.
  - Depends on: P3.3. **Needs Jon:** the repo's visibility (private or public) and approval of the task list.
  - Decision (Jon, 2026-11-22 11:35 AM ET): a separate `JongoDB/jdad-bench` repo is approved.
- [ ] **P6.2 Headless runner**
  - Deliverables: a runner that executes each task with and without JDAD (harness + MCP) across `claude -p` (note: `--bare` skips hooks, skills, plugins, MCP servers and CLAUDE.md discovery and needs `ANTHROPIC_API_KEY`, so the JDAD variant either passes everything explicitly with `--plugin-dir`, `--mcp-config` and `--settings`, or runs non-bare in an isolated `HOME`), `codex exec`, `grok -p --output-format json --no-auto-update` and `agent -p`; N runs per cell; per-run turn and budget caps; JSON results.
  - Acceptance: one task, one tool, N=2 per variant, same commit and model; a results JSON validates against a committed schema; the results show the baseline and JDAD variants loaded different instructions, skills and MCP servers (from each CLI's own listing); for each cap (turns, budget, wall-clock timeout), a forced-overrun fixture terminates the run and writes a partial result marked `capped`; spend check: the runner reads the month-to-date spend from its results files before each run and refuses to start (non-zero exit, message names the cap) when month-to-date spend plus the run's configured budget cap would exceed $20; a test with fixture results at $19.50 and a $1 run cap asserts the refusal, and one at $10 with a $1 cap asserts it starts. Every results file records the run's cost.
  - Depends on: P6.1, P4.3. **Needs Jon:** API keys for each tool the runner drives (Anthropic, OpenAI, xAI, Cursor), stored outside the repo.
  - Decision (Jon, 2026-11-22 11:35 AM ET): evals are approved with a budget capped at $20/month across all tools. The runner's budget caps must keep total spend at or under that. Spending more needs a written justification sent to Jon and his OK first.
- [ ] **P6.3 Graders**
  - Deliverables: hidden tests pass; `./verify` passes; KB-rule detectors (static checks such as pagination present or timeouts set); an LLM judge with a rubric run as a separate reviewer.
  - Acceptance: each grader has unit tests on known-good and known-bad outputs.
  - Depends on: P6.1.
- [ ] **P6.4 Skill-trigger evals**
  - Deliverables: `evals/` suite for the Claude plugin run with `claude plugin eval`, including a no-plugin baseline; CI gate threshold.
  - Acceptance: eval cases, baseline and metric are committed; the CI threshold is skill-trigger precision ≥ 0.9 and recall ≥ 0.9; a test feeds a passing and a failing results fixture to the gate and gets exit 0 and 1.
  - Depends on: P1.5.
- [ ] **P6.5 First eval report**
  - Deliverables: `docs/evals/REPORT-<date>.md` comparing baseline vs JDAD per tool and task, with cost.
  - Acceptance: `docs/evals/DESIGN.md` lists an ID and metric for every opinion under test; the report gives, per ID, mean, delta vs baseline, a 95% interval over a fixed N of paired runs, and cost; every ID whose delta is ≤ 0 or whose interval includes 0 has a keep, revise or drop decision with a reason.
  - Depends on: P6.2, P6.3.

## Phase 7: Distribution, versioning and update prompts

- [ ] **P7.1 Versioning and release policy**
  - Deliverables: ADR for semver of the plugin and package, with KB identity as git SHA + newest entry date (already in `kb_version`); `CHANGELOG.md`; a tag-triggered release workflow.
  - Acceptance: pushing a test prerelease tag (for example `v0.0.0-test.1`) in a sandbox repo or fixture ref runs the workflow, which creates a draft prerelease with notes; the version-lockstep check passes; nothing is published from the test.
  - Depends on: P5.1.
- [ ] **P7.2 Update prompts**
  - Deliverables: install docs that turn on marketplace auto-update (off by default for third-party Claude marketplaces); a compatibility manifest from the server with `plugin_min_version` (semver) kept separate from `kb_revision` (git SHA + date); `/jdad` compares its own plugin semver with `plugin_min_version` (never with the KB SHA) and tells the user when the plugin is behind; optional `SessionStart` hook that prints one line when an update exists.
  - Acceptance: the server exposes a compatibility manifest with separate fields `plugin_min_version` (semver) and `kb_revision` (git SHA + newest entry date); tests with stubbed plugin versions older than, equal to and newer than `plugin_min_version` give notice, no notice and a compatibility warning; a test asserts the server makes zero outbound network calls.
  - Depends on: P7.1.
  - Prerequisites (before auto-update is turned on anywhere): (1) the same branch protection on `main` as in P1.3, because auto-update installs whatever reaches `main`: a pull request is required before merging (no direct pushes), force pushes and branch deletion are blocked, and the rule applies to admins; the `verify` status check becomes required once GitHub Actions runs again (P5.1). Required approvals wait until reviewers use a separate GitHub account, because today every bot acts as `JongoDB` and a required approval would block every merge. Evidence: `gh api repos/JongoDB/jdad/branches/main/protection` output in the PR. This is a GitHub settings change, not a repo change. (2) every git-based plugin `source` in a marketplace Jon's hosts auto-update from is pinned by `sha` (a 40-character commit; the Claude marketplace reference's plugin sources support `ref` and `sha`), and a test fails if `.claude-plugin/marketplace.json` has a non-relative `source` without a 40-hex `sha`. **Needs Jon:** the branch protection setting.
  - Decision (Jon, 2026-11-22 11:35 AM ET): turning on marketplace auto-update on Jon's hosts is approved.
- [ ] **P7.3 Codex and Cursor package (Agent Plugins)**
  - Deliverables: compiler emits an Agent Plugins package (root `plugin.json`, `skills/`, `mcp.json`) and `.agents/plugins/marketplace.json`; install docs for Codex and Cursor.
  - Acceptance: the package validates against the Agent Plugins JSON schema. Runtime, per CLI installed: in a temp `HOME`, the named marketplace-add and install commands succeed, the plugin shows enabled with 7 tools, and a `tools/call` against a local test server succeeds. A CLI that isn't installed stays open as runtime unverified on the card.
  - Depends on: P1.5.
- [ ] **P7.4 Grok Build install proof**
  - Deliverables: install the existing Claude marketplace with `grok plugin marketplace add`, capture `grok inspect --json`; add a `.grok-plugin/marketplace.json` only if the Claude one doesn't load.
  - Acceptance: `grok inspect --json` output in the PR shows the JDAD skills and MCP server.
  - Depends on: P0.3. **Needs Jon:** a host with Grok Build installed and logged in.
- [ ] **P7.5 Install matrix and smoke scripts**
  - Deliverables: `docs/install.md` table (tool × install command × token setup × verify command); `scripts/smoke-<tool>.sh` that checks the MCP connection.
  - Acceptance: `docs/install.md` has 4 rows (Claude Code, Codex, Grok Build, Cursor); a smoke script exits 0 only after `initialize`, `tools/list` and a `kb_version` call succeed against the test server; the item is ticked only when all 4 tools have a green run attached.
  - Depends on: P7.3, P7.4.

## Phase 8: Docs site and gardening (optional)

- [ ] **P8.1 Docs site**
  - Deliverables: a static site from `docs/`, `practices/` and `ROADMAP.md`, deployed on Cloudflare Pages.
  - Acceptance: the site build exits 0 in CI and a preview URL is in the PR; a link check resolves every internal file and anchor, records every external URL's status, fails on 404 or 410, and a seeded broken link makes CI fail.
  - Depends on: P5.1. **Needs Jon:** public or private (behind Cloudflare Access). Jon's answer, "yes", approves the docs site but doesn't choose between the two.
  - Decision (Jon, 2026-11-22 11:35 AM ET): the docs site is approved.
- [ ] **P8.2 Doc-gardening routine**
  - Deliverables: a scheduled agent that checks links, research files older than 90 days, roadmap items with merged PRs but unticked boxes, and opens a fix-up PR.
  - Acceptance: against a fixture with one broken link, one research file older than 90 days and one unticked item whose PR merged, a recorded run reports all 3 and opens one PR; a rerun on the fixed fixture opens no PR.
  - Depends on: P2.5.
- [ ] **P8.3 KB stats**
  - Deliverables: `kb://stats` resource (rules per tag and topic, sources count, newest entry).
  - Acceptance: on a fixture KB, `kb://stats` returns the exact counts per tag and topic, the source count and the newest entry date; an empty KB returns zeros and a null date; the call writes nothing (snapshot test).
  - Depends on: P1.2.
