# App practices

## API [backend]
- Paginate every list endpoint. (src: guide #1) {#app.api.paginate}
  Phase: plan, review
- Return actionable errors. (src: guide #2) {#app.api.errors}
  Phase: review
- Version the public API. (src: guide #3) {#app.api.version}
  Phase: plan
- Set a timeout on every outbound call. (src: guide #4) {#app.api.timeouts}
  Applies when: the service calls other services.

## Release [ci]
- Run the full test suite before merging. (src: guide #5) {#app.release.full-suite}
  Phase: ship
- Measure before you optimise. (KB addition) {#app.release.measure}
  Phase: plan, ship
