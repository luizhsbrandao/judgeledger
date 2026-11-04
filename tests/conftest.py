"""Pytest configuration: the shared `ledger` fixture."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from judgeledger.store import Ledger  # noqa: E402


@pytest.fixture
def ledger(tmp_path):
    return Ledger.init(tmp_path / "ledger", "tester", ts="2026-01-01T00:00:00Z")
