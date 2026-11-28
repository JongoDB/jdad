"""ADR 0006 (JON-1482, roadmap P0.10): the server refuses to start if its KB can't load.

The KB root is still resolved on every call. But a root that can't load at all must stop
`jdad-mcp` before it serves anything, on stdio and on `--http`, instead of passing
`/healthz` while every tool fails. The Docker deploy doesn't set `KB_ROOT`: it serves the
KB bundled into the image (`tests/test_docker.sh` checks that inside the image).
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from jdad import server

REPO_ROOT = Path(__file__).resolve().parents[1]
MISSING = "missing practices/ or sources/"


def _bad_roots(tmp_path: Path) -> dict[str, Path]:
    (tmp_path / "only-sources" / "sources").mkdir(parents=True)
    return {"missing": tmp_path / "nope", "no-practices": tmp_path / "only-sources"}


@pytest.fixture
def transports(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record which transport main() starts, without starting it."""
    import uvicorn

    started: list[str] = []
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: started.append("http"))
    monkeypatch.setattr(server.mcp, "run", lambda *a, **k: started.append("stdio"))
    monkeypatch.delenv("JDAD_TOKEN", raising=False)
    monkeypatch.delenv("JDAD_TOKEN_FILE", raising=False)
    return started


@pytest.mark.parametrize("which", ["missing", "no-practices"])
@pytest.mark.parametrize("argv", [[], ["--http", "--port", "8765"]], ids=["stdio", "http"])
def test_a_root_that_cannot_load_stops_main_before_serving(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, transports: list[str], which: str, argv: list[str]
) -> None:
    root = _bad_roots(tmp_path)[which]
    monkeypatch.setenv("KB_ROOT", str(root))
    with pytest.raises(SystemExit) as excinfo:
        server.main(argv)
    message = str(excinfo.value.code)
    assert message.startswith("jdad-mcp: the knowledge base can't load:"), message
    assert MISSING in message and str(root) in message
    assert transports == [], "a transport started with a KB that can't load"


@pytest.mark.parametrize(("argv", "transport"), [([], "stdio"), (["--http", "--port", "8765"], "http")], ids=["stdio", "http"])
def test_a_loadable_root_still_starts_its_transport(transports: list[str], argv: list[str], transport: str) -> None:
    server.main(argv)  # KB_ROOT is the repo (conftest)
    assert transports == [transport]


def test_check_is_unchanged_and_reports_the_root_itself(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, transports: list[str]) -> None:
    monkeypatch.setenv("KB_ROOT", str(tmp_path / "nope"))
    with pytest.raises(SystemExit) as excinfo:
        server.main(["--check"])
    assert excinfo.value.code == 1  # run_check's own exit code, not the preflight's message
    assert transports == []


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.parametrize("argv", [[], ["--http", "--host", "127.0.0.1", "--port", "PORT"]], ids=["stdio", "http"])
def test_the_real_process_exits_nonzero_and_says_why(tmp_path: Path, argv: list[str]) -> None:
    """On main before ADR 0006, stdio exited 0 on a closed stdin and --http kept serving."""
    argv = [str(_free_port()) if a == "PORT" else a for a in argv]
    env = {k: v for k, v in os.environ.items() if k not in {"JDAD_TOKEN", "JDAD_TOKEN_FILE"}}
    env["KB_ROOT"] = str(tmp_path / "nope")
    try:
        proc = subprocess.run(
            [sys.executable, "-c", "from jdad.server import main; main()", *argv],
            check=False,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("jdad-mcp kept running with a KB root that can't load")
    assert proc.returncode != 0, proc.stderr
    assert MISSING in proc.stderr, proc.stderr


@pytest.mark.parametrize("path", ["Dockerfile", "deploy/docker-compose.yml", "deploy/compose.legacy-token.yml"])
def test_the_docker_deploy_does_not_set_kb_root(path: str) -> None:
    """ADR 0006 decision 1: the image serves the KB bundled at build time."""
    assert "KB_ROOT" not in (REPO_ROOT / path).read_text()
