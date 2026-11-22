from __future__ import annotations

from pathlib import Path

import pytest
from mcp import Client

from jdad.server import mcp

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def kb_root(monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("KB_ROOT", str(REPO_ROOT))
    monkeypatch.delenv("JDAD_TOKEN", raising=False)
    return REPO_ROOT


@pytest.fixture
async def client():
    async with Client(mcp, raise_exceptions=True) as connected:
        yield connected
