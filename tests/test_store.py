"""Storage: append-only ledger, event log, state replay."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from judgeledger.model import Evidence, IntegrityError
from judgeledger.store import EVENTS_FILE, LEDGER_FILE, Ledger
from helpers import EVIDENCE, add


def test_init_creates_both_files_and_a_genesis_event(tmp_path) -> None:
    ledger = Ledger.init(tmp_path / "led", "tester", ts="2026-01-01T00:00:00Z")
    assert (ledger.root / LEDGER_FILE).read_text() == ""
    events = ledger.events()
    assert len(events) == 1
    assert events[0]["action"] == "init"
    assert events[0]["prev_hash"] == "0" * 64


def test_init_twice_is_refused(ledger) -> None:
    with pytest.raises(IntegrityError, match="already initialised"):
        Ledger.init(ledger.root, "tester")


def test_ids_are_sequential(ledger) -> None:
    first = add(ledger, outcome=None)
    second = add(ledger, outcome=None)
    assert (first.id, second.id) == ("E001", "E002")


def test_ledger_is_append_only(ledger) -> None:
    add(ledger, outcome=None)
    first_line = ledger.ledger_path.read_text().splitlines()[0]
    add(ledger, outcome=None)
    lines = ledger.ledger_path.read_text().splitlines()
    assert len(lines) == 2
    assert lines[0] == first_line


def test_open_twice_is_refused(ledger) -> None:
    entry = add(ledger, outcome=None)
    with pytest.raises(IntegrityError, match="only a draft"):
        ledger.open_entry(entry.id, "tester")


def test_resolve_requires_an_open_entry(ledger) -> None:
    entry = ledger.add(
        question="Q?",
        criteria="Stated in the official published record",
        due="2026-06-30",
        kind="interval",
        actor="tester",
        interval=(0.4, 0.6),
        created_at="2026-01-01T12:00:00Z",
    )
    with pytest.raises(IntegrityError, match="only an open entry"):
        ledger.resolve(entry.id, outcome=1, evidence=EVIDENCE, resolver="tester")


def test_resolve_requires_a_source(ledger) -> None:
    entry = add(ledger, outcome=None)
    with pytest.raises(IntegrityError, match="citation"):
        ledger.resolve(
            entry.id, outcome=1, evidence=Evidence(), resolver="tester"
        )


def test_resolve_records_the_payload(ledger) -> None:
    entry = add(ledger, outcome=None)
    payload = ledger.resolve(
        entry.id,
        outcome=0,
        evidence=Evidence(
            citation="Doc", url="https://example.org/x", excerpt="quoted"
        ),
        resolver="tester",
        resolved_at="2026-06-30T12:00:00Z",
    )
    assert payload["outcome"] == 0
    assert payload["late"] is False
    assert ledger.state()[entry.id]["status"] == "resolved"


def test_resolution_after_the_due_date_is_flagged_late(ledger) -> None:
    entry = add(ledger, outcome=None)
    payload = ledger.resolve(
        entry.id,
        outcome=1,
        evidence=EVIDENCE,
        resolver="tester",
        resolved_at="2026-07-15T12:00:00Z",
    )
    assert payload["late"] is True


def test_void_requires_a_reason(ledger) -> None:
    entry = add(ledger, outcome=None)
    with pytest.raises(IntegrityError, match="reason"):
        ledger.void(entry.id, reason="  ", resolver="tester")


def test_void_after_resolution_is_refused(ledger) -> None:
    entry = add(ledger, outcome=1)
    with pytest.raises(IntegrityError, match="only a draft or open"):
        ledger.void(entry.id, reason="changed my mind", resolver="tester")


def test_state_replays_every_status(ledger) -> None:
    draft = add(ledger, outcome=None)
    ledger.void(draft.id, reason="ambiguous criterion", resolver="tester")
    open_entry = ledger.add(
        question="Q2?",
        criteria="Stated in the official published record",
        due="2026-06-30",
        kind="point",
        actor="tester",
        point=0.5,
        created_at="2026-01-01T12:00:00Z",
    )
    ledger.open_entry(open_entry.id, "tester")
    resolved = add(ledger, outcome=1)
    state = ledger.state()
    assert state[draft.id]["status"] == "void"
    assert state[open_entry.id]["status"] == "open"
    assert state[resolved.id]["status"] == "resolved"


def test_missing_ledger_is_refused(tmp_path) -> None:
    with pytest.raises(IntegrityError, match="no ledger here"):
        Ledger(tmp_path / "nope").require()


def test_events_are_hash_chained(ledger) -> None:
    add(ledger, outcome=1)
    events = ledger.events()
    assert events[0]["prev_hash"] == "0" * 64
    for previous, current in zip(events, events[1:]):
        assert current["prev_hash"] == previous["hash"]
    assert ledger.verify() == []


def test_entry_line_is_canonical_json(ledger) -> None:
    add(ledger, outcome=None)
    line = ledger.ledger_path.read_text().splitlines()[0]
    parsed = json.loads(line)
    assert json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":")) == line
