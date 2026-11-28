# 0006: The hosted server's KB root: bundled data, no required `KB_ROOT`

- Status: Accepted (Jon, 2026-11-27 9:45 PM CT, question 348a; implemented in JON-1482)
- Date: 2026-11-27
- Deciders: Jon (approve), authoring agent (JON-1482)

## Context

Roadmap P0.10 (KB poisoning defences, JON-1341, PR #8) has one open acceptance criterion: "a decision recorded on whether the hosted server requires `KB_ROOT`". The question came from Checker's pass of #8: should the hosted server have to be told where its KB is (for example `KB_ROOT=/app/kb` in the Dockerfile), or may it keep finding it on its own?

How the root is found today (`resolve_kb_root` in `src/jdad/kb.py`):

1. an explicit argument;
2. `KB_ROOT`;
3. the jdad source checkout the module runs from (an editable install);
4. the package data bundled in the wheel (a `data` directory inside the installed `jdad` package).

It never walks up from the current directory, which was threat 2 in [the threat model](../threat-model.md) ("Wrong KB served"). These tests pin that order: `test_resolve_kb_root_ignores_the_current_directory`, `test_kb_root_env_still_wins` and `test_installed_wheel_layout_uses_bundled_data_not_parents` in `tests/test_kb.py`, and `test_missing_kb_root_fails` in `tests/test_check.py`.

The two deploy layouts:

- **Docker (the live deploy, [ADR 0005](0005-hosted-deploy-cloudflare-full-strict.md)).**
  - The Dockerfile copies `practices/` and `sources/`, installs the package with `uv sync --no-editable`, and runs `jdad-mcp --check` from `/` at build time, so a KB that doesn't load fails the build.
  - The runtime stage copies only the venv. There's no checkout in the image, and neither the Dockerfile nor the compose file sets `KB_ROOT`.
  - So the server serves the bundled copy, taken at the image's build SHA. `kb_version` takes its SHA from `JDAD_GIT_SHA`, which is set at build time.
- **Legacy systemd** (`deploy/jdad.service`): sets `KB_ROOT=/opt/jdad`, the checkout.

What was checked for this ADR (2026-11-27, main 2eeb396; JON-1482 has the output):

- **Install.** A wheel built from main and installed non-editable in a clean venv, the same layout as the image. Run from a directory that has its own `practices/`, it resolves to the bundled package data; the source checkout is `None`, and the stray `practices/` isn't used.
- **Bundled data.** It holds the same 10 files as `git ls-files practices sources`, byte for byte.
- **A bad `KB_ROOT`.** `KB_ROOT=/nope`, or a directory without `practices/`, raises `FileNotFoundError: KB root … is missing practices/ or sources/`, and `jdad-mcp --check` exits 1.
- **A running server with a bad `KB_ROOT`.** `jdad-mcp --http` with `KB_ROOT=/nope` **still starts**:
  - `/healthz` returns `200 {"status":"ok"}`;
  - `initialize` succeeds;
  - every tool call fails with the generic `Error executing tool …`, and the server logs a traceback.
  The root is resolved on each call, not at start-up, so a bad `KB_ROOT` doesn't show up until a tool call fails.
- **Inside the built image:** Docker was off on the authoring machine, so the wheel install stood in for the image while this ADR was Proposed. `tests/test_docker.sh` now checks the image itself in CI: `resolve_kb_root()` in the image is the bundled `…/site-packages/jdad/data`, and `jdad-mcp` with `KB_ROOT=/nope` exits non-zero and names the problem.

## Decision

1. **The hosted (Docker) server does not require `KB_ROOT`.** It serves the KB bundled into the image at build time. The Dockerfile and compose file don't set `KB_ROOT`, and an operator shouldn't set it on the droplet.
2. **The KB root is never taken from the current directory**, in any layout. The tests above keep this.
3. **A KB root that can't be loaded must stop the server at start-up, not pass `/healthz`.** `jdad-mcp --http` and stdio resolve the KB root once before serving, and exit non-zero with the `FileNotFoundError` message when the root, its `practices/` or its `sources/` is missing. The start-up check doesn't list or parse the practice files to decide: an unreadable `practices/` directory lists as empty, so the server still starts. This applies whether the root came from `KB_ROOT`, the checkout or the bundled data. `require_kb()` in `src/jdad/server.py` does this (JON-1482), and `tests/test_startup.py` covers it in process and as a real process. Files skipped with a warning (unreadable, oversized, symlinked) don't stop the server.
4. The legacy systemd layout keeps `KB_ROOT=/opt/jdad`. Decision 3 covers a mistyped value there too.

An agent can check compliance:
- `grep -n KB_ROOT Dockerfile` (and the compose files) finds nothing, which `tests/test_startup.py` checks;
- `tests/test_kb.py`'s resolution tests pass;
- `tests/test_startup.py` shows a missing or incomplete KB root stopping `jdad-mcp` with a non-zero exit before any transport starts, and `tests/test_docker.sh` shows the same inside the image.

## Consequences

- **Easier.**
  - The image is self-contained. What it serves is exactly what passed `jdad-mcp --check` at build time, at the build's SHA.
  - There's no extra variable to get wrong on the droplet.
  - A rollback to an older image serves that image's KB, which is what a rollback should do.
- **Harder.**
  - Changing the hosted KB always means a rebuild and redeploy (already true: `update-docker.sh` rebuilds on every deploy).
  - Pointing a container at a mounted KB for debugging means setting `KB_ROOT` by hand. That still works, because `KB_ROOT` keeps priority.
- **To maintain.**
  - The `force-include` of `practices/` and `sources/` in `pyproject.toml`.
  - The build-time `--check` in the Dockerfile.
  - Decision 3's start-up check, `require_kb()`.

## Alternatives considered

- **(b) Set `KB_ROOT=/app/kb` in the Dockerfile and copy the KB there.** It makes the root explicit. But it ships a second copy of the KB next to the bundled one, adds an image change and a redeploy, and stops no threat the current order doesn't already stop. It also leaves the start-up gap in decision 3 open.
- **(c) Refuse `--http` on a non-loopback bind unless `KB_ROOT` is set.** It forces operators to be explicit. But on its own it breaks the current Docker deploy (it would need (b) as well). It doesn't address threat 2, which the resolution order already handles. And a required variable is one more thing that can be set wrong: today a wrong value gives a green `/healthz` and failing tools.
- **(a) as is, without decision 3.** It's acceptable for the Docker deploy, where `KB_ROOT` is unset and the build checks the KB. But any layout that sets `KB_ROOT` (systemd, a manual run) can still serve a healthy-looking endpoint with no KB. Hence decision 3.
