# API design (search fixture)
## Pagination [backend]
- Paginate every list endpoint with a cursor, not an offset. (KB addition) {#api.pagination.cursor}
- Cap page size at 100 items and document the default. (KB addition) {#api.pagination.page-size}
## Errors [backend]
- Return problem+json bodies with a stable error code. (KB addition) {#api.errors.problem-json}
- Never leak stack traces in production error responses. (KB addition) {#api.errors.no-stack-traces}
## Timeouts and retries [backend] [infra]
- Every outbound HTTP call gets a timeout. (KB addition) {#api.resilience.timeouts}
- Retry idempotent requests with exponential backoff and jitter. (KB addition) {#api.resilience.retry-backoff}
- Use idempotency keys on POST endpoints that charge money. (KB addition) {#api.resilience.idempotency-keys}
