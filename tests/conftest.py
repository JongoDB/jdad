from __future__ import annotations

import re
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
def newest_entry() -> str:
    """The newest YYYY-MM-DD file-name date under sources/ and practices/.

    Tests on the real KB compare kb_version with this instead of a pinned
    date, so the next ingest doesn't break them (Checker on #33, JON-1363).
    Exact dates stay pinned on fixture KBs (test_kb_files, test_source_schema).
    """
    names = [p.name for d in ("sources", "practices") for p in (REPO_ROOT / d).glob("*.md")]
    dates = [name[:10] for name in names if re.match(r"\d{4}-\d{2}-\d{2}-", name)]
    assert dates, "no dated KB files"
    return max(dates)


@pytest.fixture
async def client():
    async with Client(mcp, raise_exceptions=True) as connected:
        yield connected
