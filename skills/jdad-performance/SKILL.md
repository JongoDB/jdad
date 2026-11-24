---
name: jdad-performance
description: Use when building, reviewing, or speeding up an application — page load, API or backend latency, N+1 queries, indexes, connection pooling, caching, CDNs, job queues, OpenTelemetry, Core Web Vitals, or tests on slow devices and networks. Applies Jon's JDAD performance checklist.
metadata:
  generated: jdad build from catalog/skills/jdad-performance/SKILL.md; do not edit
---

# JDAD performance

These rules come from `practices/performance.md` in the JDAD knowledge base. Prefer the jdad MCP tools (`get_practice` with `performance`, or `get_checklist` with the tags below) when they are available, so you are on the latest SHA. Cite rules in the plan and the PR by rule ID (for example `perf.db.n-plus-one`) and source.

Start with Rule zero. Each rule ends with its citation and its ID.

## Rule zero [frontend] [backend] [db] [infra] [observability] [testing]

- Measure first: profile or trace, fix the top bottleneck, re-measure, and put before/after numbers in the PR. Don't shotgun all of these. (KB addition) {#perf.rule-zero}

## Frontend [frontend]

- Skeleton loaders for async content. (src: breakingbreach #1) {#perf.frontend.skeleton-loaders}
  Phase: plan, review
- Optimistic UI on user actions, with rollback on error. (src: breakingbreach #14) {#perf.frontend.optimistic-ui}
  Phase: plan, review
- Images as AVIF/WebP. (src: breakingbreach #2) {#perf.frontend.modern-image-formats}
  Phase: review
- Lazy-load images below the fold. (src: breakingbreach #15) {#perf.frontend.lazy-images}
  Phase: review
- Self-host fonts, only the weights used. (src: breakingbreach #29) {#perf.frontend.self-host-fonts}
  Phase: review
- Code-split per route. (src: breakingbreach #22) {#perf.frontend.code-split}
  Phase: plan, review
- Defer third-party scripts (chat, analytics, ads) until after load. (src: breakingbreach #21) {#perf.frontend.defer-third-party}
  Phase: review
- Drop unused deps and check bundle size in CI. (src: breakingbreach #11) {#perf.frontend.unused-deps}
  Phase: review, ship
- SSR/SSG for content pages. (src: breakingbreach #20) {#perf.frontend.ssr-ssg}
  Phase: plan
- Virtualize long lists. (src: breakingbreach #23) {#perf.frontend.virtualize-lists}
  Phase: review
- Memoize to stop needless re-renders. (src: breakingbreach #26) {#perf.frontend.memoize}
  Phase: review
- Debounce search/autocomplete. (src: breakingbreach #4) {#perf.frontend.debounce-search}
  Phase: review
- Dedupe identical in-flight requests (a shared query cache). (src: breakingbreach #3) {#perf.frontend.dedupe-requests}
  Phase: review
- Stream LLM output token by token. (src: breakingbreach #13) {#perf.frontend.stream-llm}
  Phase: plan, review

## Backend and API [backend]

- Paginate every list endpoint. (src: breakingbreach #5) {#perf.backend.paginate}
  Phase: plan, review
- Run independent calls in parallel. (src: breakingbreach #16) {#perf.backend.parallel-calls}
  Phase: review
- Every outbound call gets a timeout plus a user-facing fallback or retry. (src: breakingbreach #12) {#perf.backend.outbound-timeouts}
  Phase: review
- Slow work (PDFs, email, resizes) goes to a job queue/worker. (src: breakingbreach #7) {#perf.backend.job-queue}
  Phase: plan
- Cache hot reads (e.g. Redis) with explicit TTL/invalidation. (src: breakingbreach #10) {#perf.backend.cache-hot-reads}
  Phase: plan, review

## Database [db]

- Kill N+1 (batch/join). (src: breakingbreach #8) {#perf.db.n-plus-one}
  Phase: review
- Index the columns you filter on. (src: breakingbreach #17) {#perf.db.index-filters}
  Phase: review
- Select only needed columns (also keeps private fields out). (src: breakingbreach #24) {#perf.db.select-columns}
  Phase: review
- Use connection pooling. (src: breakingbreach #25) {#perf.db.connection-pooling}
  Phase: ship
- App servers in the same region as the DB. (src: breakingbreach #19) {#perf.db.colocate}
  Phase: plan, ship

## Delivery and infra [infra]

- CDN for static assets. (src: breakingbreach #6) {#perf.infra.cdn}
  Phase: ship
- Brotli/Gzip. (src: breakingbreach #9) {#perf.infra.compression}
  Phase: ship
- Long cache headers on hashed assets. (src: breakingbreach #27) {#perf.infra.cache-headers}
  Phase: ship
- Load balancer with health checks. (src: breakingbreach #28) {#perf.infra.load-balancer}
  Applies when: there's more than one instance.
  Phase: ship

## Observability [observability]

- OpenTelemetry traces on backend requests. (src: breakingbreach #18) {#perf.observability.otel-traces}
  Phase: plan, ship
- Real-user monitoring (Core Web Vitals). (src: breakingbreach #30) {#perf.observability.rum}
  Phase: ship

## Testing [testing]

- Test with CPU throttling and Fast 3G (Lighthouse/DevTools) before shipping. (src: breakingbreach #31) {#perf.testing.slow-device}
  Phase: ship
