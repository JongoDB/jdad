# syntax=docker/dockerfile:1
# Multi-stage image for jdad-mcp. The runtime bind is 0.0.0.0, so
# JDAD_TOKEN must be set; --allow-no-auth is not used here.
# Public deploy enables TLS on 8443 via compose (see deploy/docker-compose.yml).

FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b AS builder

COPY --from=ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff \
    /uv /usr/local/bin/uv

WORKDIR /src
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_PREFERENCE=only-system \
    UV_PROJECT_ENVIRONMENT=/app/.venv

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY practices ./practices
COPY sources ./sources

# Install the project (not editable) so practices/ and sources/ are
# bundled into the venv as package data.
RUN uv sync --frozen --no-dev --no-editable

# Refuse to build an image whose KB doesn't load. This runs against the
# installed package's bundled data (run from / so no checkout is found),
# i.e. exactly what ships.
RUN cd / && /app/.venv/bin/jdad-mcp --check

FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b AS runtime

ARG JDAD_GIT_SHA=unknown
ENV JDAD_GIT_SHA=$JDAD_GIT_SHA
# This image reads the token from JDAD_TOKEN_FILE. update-docker.sh checks the
# label before a rollback: images without it read only JDAD_TOKEN and need
# deploy/compose.legacy-token.yml to start.
LABEL io.jdad.token-file="1"

RUN useradd --system --user-group --uid 999 --create-home --home-dir /app \
    --shell /usr/sbin/nologin jdad \
    && chmod 755 /app
# useradd creates /app as 0700. Compose runs as the deploy uid so a 0600
# TLS key is readable without chown; /app must stay world-traversable so
# that uid can exec /app/.venv/bin/jdad-mcp.

# Root-owned venv: the app user can execute it but cannot overwrite the code.
COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER jdad
WORKDIR /app
EXPOSE 8765 8443

# Default HEALTHCHECK is HTTP on 8765 (docker run without TLS).
# The compose file overrides this for HTTPS on 8443.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/healthz', timeout=4).read()"

CMD ["jdad-mcp", "--http", "--host", "0.0.0.0", "--port", "8765"]
