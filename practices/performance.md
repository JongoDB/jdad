# Performance (production-grade defaults)
Rule zero (KB addition, not from the source): measure first. Profile or trace, fix the top bottleneck, re-measure, and put before/after numbers in the PR. Don't shotgun all of these.
## Frontend [frontend]
- Skeleton loaders for async content; optimistic UI on user actions, with rollback on error. (src: breakingbreach #1, #14)
- Images as AVIF/WebP, lazy-load below the fold; self-host fonts, only the weights used. (#2, #15, #29)
- Code-split per route; defer third-party scripts (chat, analytics, ads) until after load; drop unused deps and check bundle size in CI. (#11, #21, #22)
- SSR/SSG for content pages. (#20)
- Virtualize long lists; memoize to stop needless re-renders. (#23, #26)
- Debounce search/autocomplete; dedupe identical in-flight requests (a shared query cache). (#3, #4)
- Stream LLM output token by token. (#13)
## Backend and API [backend]
- Paginate every list endpoint. (#5)
- Run independent calls in parallel. (#16)
- Every outbound call gets a timeout plus a user-facing fallback or retry. (#12)
- Slow work (PDFs, email, resizes) goes to a job queue/worker. (#7)
- Cache hot reads (e.g. Redis) with explicit TTL/invalidation. (#10)
## Database [db]
- Kill N+1 (batch/join); index the columns you filter on; select only needed columns (also keeps private fields out); use connection pooling. (#8, #17, #24, #25)
- App servers in the same region as the DB. (#19)
## Delivery and infra [infra]
- CDN for static assets, Brotli/Gzip, long cache headers on hashed assets; load balancer with health checks once there's more than one instance. (#6, #9, #27, #28)
## Observability and testing [observability] [testing]
- OpenTelemetry traces on backend requests; real-user monitoring (Core Web Vitals). (#18, #30)
- Test with CPU throttling and Fast 3G (Lighthouse/DevTools) before shipping. (#31)
