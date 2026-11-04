"""Integrity: any edit to the past must surface as an error, not as a quiet rewrite."""

from __future__ import annotations

import json

import pytest

from judgeledger.model import IntegrityError
from judgeledger.store import EVENTS_FILE, LEDGER_FILE
from helpers import add


def _rewrite(path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_clean_ledger_validates(ledger) -> None:
    add(ledger, outcome=1)
    errors, _warnings = ledger.validate()
    assert errors == []


def test_editing_a_locked_criterion_is_detected(ledger) -> None:
    add(ledger, outcome=1)
    lines = ledger.ledger_path.read_text().splitlines()
    record = json.loads(lines[0])
    record["criteria"] = "Something much easier that I only thought of afterwards"
    lines[0] = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    _rewrite(ledger.ledger_path, lines)

    errors = ledger.verify()
    assert any("altered after creation" in error for error in errors)
    assert any("hash mismatch" in error for error in errors)

    errors, _warnings = ledger.validate()
    assert errors


def test_editing_an_event_is_detected(ledger) -> None:
    add(ledger, outcome=1)
    lines = ledger.events_path.read_text().splitlines()
    event = json.loads(lines[-1])
    event["payload"]["outcome"] = 0
    lines[-1] = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    _rewrite(ledger.events_path, lines)

    errors = ledger.verify()
    assert any("hash mismatch" in error for error in errors)


def test_removing_an_event_breaks_the_chain(ledger) -> None:
    add(ledger, outcome=None)
    add(ledger, outcome=None)
    lines = ledger.events_path.read_text().splitlines()
    del lines[1]
    _rewrite(ledger.events_path, lines)

    errors = ledger.verify()
    assert any("prev_hash" in error or "expected seq" in error for error in errors)


def test_duplicate_entry_ids_are_detected(ledger) -> None:
    add(ledger, outcome=None)
    first = ledger.ledger_path.read_text().splitlines()[0]
    with open(ledger.ledger_path, "a", encoding="utf-8") as handle:
        handle.write(first + "\n")
    with pytest.raises(IntegrityError, match="duplicate entry id"):
        ledger.entries()


def test_invalid_json_line_is_reported_with_its_number(ledger) -> None:
    add(ledger, outcome=None)
    with open(ledger.ledger_path, "a", encoding="utf-8") as handle:
        handle.write("{not json}\n")
    with pytest.raises(IntegrityError, match=f"{LEDGER_FILE} line 2"):
        ledger.entries()


def test_event_for_an_unknown_entry_is_detected(ledger) -> None:
    add(ledger, outcome=None)
    lines = ledger.events_path.read_text().splitlines()
    event = json.loads(lines[-1])
    event["entry"] = "E999"
    event.pop("hash")
    from judgeledger.store import event_digest

    event["hash"] = event_digest(event)
    lines[-1] = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    _rewrite(ledger.events_path, lines)

    with pytest.raises(IntegrityError, match="unknown entry"):
        ledger.state()


def test_missing_create_event_is_detected(ledger) -> None:
    add(ledger, outcome=None)
    lines = ledger.events_path.read_text().splitlines()
    # drop the create event (second line: init, then create, then open)
    del lines[1]
    _rewrite(ledger.events_path, lines)

    errors = ledger.verify()
    assert any("no create event" in error for error in errors)


def test_validate_warns_about_overdue_open_entries(ledger) -> None:
    ledger.add(
        question="Late question?",
        criteria="Stated in the official published record",
        due="2026-02-01",
        kind="point",
        actor="tester",
        point=0.5,
        created_at="2026-01-01T12:00:00Z",
    )
    ledger.open_entry("E001", "tester")
    _errors, warnings = ledger.validate()
    assert any("past the due date" in warning for warning in warnings)


def test_validate_warns_about_missing_origin(ledger) -> None:
    add(ledger, outcome=None)
    _errors, warnings = ledger.validate()
    assert any("without an origin" in warning for warning in warnings)


def test_events_file_constant_matches_ledger(ledger) -> None:
    assert ledger.events_path.name == EVENTS_FILE
