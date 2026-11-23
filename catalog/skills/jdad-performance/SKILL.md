---
name: jdad-performance
description: Use when building, reviewing, or speeding up an application — page load, API or backend latency, N+1 queries, indexes, connection pooling, caching, CDNs, job queues, OpenTelemetry, Core Web Vitals, or tests on slow devices and networks. Applies Jon's JDAD performance checklist.
---

# JDAD performance

These rules come from `practices/performance.md` in the JDAD knowledge base. Prefer the jdad MCP tools (`get_practice` with `performance`, or `get_checklist` with the tags below) when they are available, so you are on the latest SHA. Cite rules in the plan and the PR by rule ID (for example `perf.db.n-plus-one`) and source.

Start with Rule zero. Each rule ends with its citation and its ID.

## Rule zero [frontend] [backend] [db] [infra] [observability] [testing]

- Measure first: profile or trace, fix the top bottleneck, re-measure, and put before/after numbers in the PR. Don't shotgun all of these. (KB addition) {#perf.rule-zero}

## Frontend [frontend]

- Skeleton loaders for async content. (src: breakingbreach #1) {#perf.frontend.skeleton-loaders}
- Optimistic UI on user actions, with rollback on error. (src: breakingbreach #14) {#perf.frontend.optimistic-ui}
- Images as AVIF/WebP. (src: breakingbreach #2) {#perf.frontend.modern-image-formats}
- Lazy-load images below the fold. (src: breakingbreach #15) {#perf.frontend.lazy-images}
- Self-host fonts, only the weights used. (src: breakingbreach #29) {#perf.frontend.self-host-fonts}
- Code-split per route. (src: breakingbreach #22) {#perf.frontend.code-split}
- Defer third-party scripts (chat, analytics, ads) until after load. (src: breakingbreach #21) {#perf.frontend.defer-third-party}
- Drop unused deps and check bundle size in CI. (src: breakingbreach #11) {#perf.frontend.unused-deps}
- SSR/SSG for content pages. (src: breakingbreach #20) {#perf.frontend.ssr-ssg}
- Virtualize long lists. (src: breakingbreach #23) {#perf.frontend.virtualize-lists}
- Memoize to stop needless re-renders. (src: breakingbreach #26) {#perf.frontend.memoize}
- Debounce search/autocomplete. (src: breakingbreach #4) {#perf.frontend.debounce-search}
- Dedupe identical in-flight requests (a shared query cache). (src: breakingbreach #3) {#perf.frontend.dedupe-requests}
- Stream LLM output token by token. (src: breakingbreach #13) {#perf.frontend.stream-llm}

## Backend and API [backend]

- Paginate every list endpoint. (src: breakingbreach #5) {#perf.backend.paginate}
- Run independent calls in parallel. (src: breakingbreach #16) {#perf.backend.parallel-calls}
- Every outbound call gets a timeout plus a user-facing fallback or retry. (src: breakingbreach #12) {#perf.backend.outbound-timeouts}
- Slow work (PDFs, email, resizes) goes to a job queue/worker. (src: breakingbreach #7) {#perf.backend.job-queue}
- Cache hot reads (e.g. Redis) with explicit TTL/invalidation. (src: breakingbreach #10) {#perf.backend.cache-hot-reads}

## Database [db]

- Kill N+1 (batch/join). (src: breakingbreach #8) {#perf.db.n-plus-one}
- Index the columns you filter on. (src: breakingbreach #17) {#perf.db.index-filters}
- Select only needed columns (also keeps private fields out). (src: breakingbreach #24) {#perf.db.select-columns}
- Use connection pooling. (src: breakingbreach #25) {#perf.db.connection-pooling}
- App servers in the same region as the DB. (src: breakingbreach #19) {#perf.db.colocate}

## Delivery and infra [infra]

- CDN for static assets. (src: breakingbreach #6) {#perf.infra.cdn}
- Brotli/Gzip. (src: breakingbreach #9) {#perf.infra.compression}
- Long cache headers on hashed assets. (src: breakingbreach #27) {#perf.infra.cache-headers}
- Load balancer with health checks. (src: breakingbreach #28) {#perf.infra.load-balancer}
  Applies when: there's more than one instance.

## Observability [observability]

- OpenTelemetry traces on backend requests. (src: breakingbreach #18) {#perf.observability.otel-traces}
- Real-user monitoring (Core Web Vitals). (src: breakingbreach #30) {#perf.observability.rum}

## Testing [testing]

- Test with CPU throttling and Fast 3G (Lighthouse/DevTools) before shipping. (src: breakingbreach #31) {#perf.testing.slow-device}
