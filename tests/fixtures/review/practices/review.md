# Review fixture

One rule per tag, so a review for one tag set can be checked against the others.

## Frontend [frontend]
- Lazy-load images below the fold. (KB addition) {#rev.frontend.lazy}

## Backend [backend]
- Put a timeout on every outbound call. (KB addition) {#rev.backend.timeouts}

## Database [db]
- Index the columns you filter on. (KB addition) {#rev.db.index}

## Infrastructure [infra]
- Give the container a memory limit. (KB addition) {#rev.infra.limits}

## Tests [testing]
- Test the failure path, not only the happy path. (KB addition) {#rev.testing.failures}

## Pipelines [ci]
- Make the required check block merges. (KB addition) {#rev.ci.required}

## Dependencies [supply-chain]
- Commit the lockfile. (KB addition) {#rev.supply.lockfile}

## Review only [backend]
- Return actionable errors. (KB addition) {#rev.backend.errors}
  Phase: review
- Plan the API version up front. (KB addition) {#rev.backend.version}
  Phase: plan
