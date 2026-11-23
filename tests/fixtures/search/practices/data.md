# Data (search fixture)
## Queries [db]
- Kill N+1 queries with batching or a join. (KB addition) {#data.queries.n-plus-one}
- Index the columns you filter and sort on. (KB addition) {#data.queries.indexes}
- Select only the columns you need. (KB addition) {#data.queries.select-columns}
## Migrations [db] [infra]
- Make every migration backward compatible with the running release. (KB addition) {#data.migrations.backward-compatible}
- Add an index concurrently on large tables. (KB addition) {#data.migrations.concurrent-index}
  Applies when: the table has more than a million rows.
## Caching [backend] [db]
- Cache hot reads with an explicit TTL. (KB addition) {#data.cache.ttl}
- Invalidate the cache on write, not on a timer. (KB addition) {#data.cache.invalidate-on-write}
