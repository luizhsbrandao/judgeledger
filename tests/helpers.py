"""Shared fixtures and helpers."""

from __future__ import annotations

import pytest

from judgeledger.model import Evidence
from judgeledger.store import Ledger

CREATED = "2026-01-01T12:00:00Z"
DUE = "2026-06-30"
EVIDENCE = Evidence(citation="Synthetic official record", url="https://example.org/record")


@pytest.fixture
def ledger(tmp_path):
    return Ledger.init(tmp_path / "ledger", "tester", ts="2026-01-01T00:00:00Z")


def add(
    ledger: Ledger,
    *,
    interval=(0.4, 0.6),
    point=None,
    outcome=1,
    due=DUE,
    created=CREATED,
    question="Does the demo event happen?",
    criteria="Stated in the official published record",
    tags=None,
    origin=None,
):
    """Add, open and optionally resolve one entry."""
    kind = "point" if point is not None else "interval"
    entry = ledger.add(
        question=question,
        criteria=criteria,
        due=due,
        kind=kind,
        actor="tester",
        point=point,
        interval=None if point is not None else interval,
        tags=tags,
        origin=origin,
        created_at=created,
    )
    ledger.open_entry(entry.id, "tester", ts=created)
    if outcome is not None:
        ledger.resolve(
            entry.id,
            outcome=outcome,
            evidence=EVIDENCE,
            resolver="tester",
            resolved_at=f"{due}T12:00:00Z",
        )
    return entry


def seed(ledger: Ledger, count: int = 20) -> list[str]:
    """A ledger with `count` resolved entries, half hits and half misses."""
    ids = []
    for index in range(count):
        hit = index % 2 == 0
        entry = add(
            ledger,
            interval=(0.6, 0.9) if hit else (0.1, 0.4),
            outcome=1 if hit else 0,
            question=f"Seeded judgment {index:02d}",
        )
        ids.append(entry.id)
    return ids
