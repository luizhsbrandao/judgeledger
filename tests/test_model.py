"""Model rules: the integrity constraints that make a judgment auditable."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from judgeledger.model import (
    MAX_EXCERPT_CHARS,
    Entry,
    Evidence,
    IntegrityError,
    build_entry,
    resolution_errors,
)

CREATED = "2026-01-01T12:00:00Z"
DUE = "2026-06-30"


def make(**overrides):
    kwargs = dict(
        entry_id="E001",
        question="Does the demo event happen?",
        criteria="Stated in the official published record",
        due=DUE,
        kind="interval",
        actor="tester",
        created_at=CREATED,
        interval=(0.4, 0.6),
    )
    kwargs.update(overrides)
    return build_entry(**kwargs)


def test_horizon_is_derived_from_dates() -> None:
    entry = make()
    assert entry.horizon_days == 180
    assert entry.as_forecast() == "[0.40, 0.60]"


def test_point_forecast_roundtrip() -> None:
    entry = make(kind="point", interval=None, point=0.7)
    restored = Entry.from_dict(json.loads(json.dumps(entry.to_dict())))
    assert restored == entry
    assert restored.as_forecast() == "0.70"


def test_backdated_judgment_is_rejected() -> None:
    with pytest.raises(IntegrityError, match="cannot be backdated"):
        make(due="2025-12-31")


def test_short_criteria_are_rejected() -> None:
    with pytest.raises(IntegrityError, match="criteria"):
        make(criteria="too short")


def test_point_outside_the_unit_interval_is_rejected() -> None:
    with pytest.raises(IntegrityError, match="outside"):
        make(kind="point", interval=None, point=1.4)


def test_inverted_interval_is_rejected() -> None:
    with pytest.raises(IntegrityError, match="lower bound"):
        make(interval=(0.8, 0.2))


def test_equal_bounds_are_rejected_for_intervals() -> None:
    with pytest.raises(IntegrityError, match="lower bound"):
        make(interval=(0.5, 0.5))


def test_point_and_interval_together_are_rejected() -> None:
    kwargs = dict(
        entry_id="E001",
        question="Q?",
        criteria="Stated in the official published record",
        due=DUE,
        kind="point",
        actor="tester",
        created_at=CREATED,
        point=0.5,
        interval=(0.4, 0.6),
    )
    with pytest.raises(IntegrityError, match="either"):
        build_entry(**kwargs)


def test_empty_question_is_reported_by_errors() -> None:
    entry = make()
    entry.question = ""
    assert any("question is empty" in problem for problem in entry.errors())


def test_evidence_needs_citation_and_locator() -> None:
    problems = Evidence(citation="", url="").errors()
    assert any("citation" in problem for problem in problems)
    assert any("url or archive_url" in problem for problem in problems)


def test_archive_url_counts_as_a_locator() -> None:
    evidence = Evidence(citation="Doc", archive_url="https://web.archive.org/x")
    assert evidence.errors() == []


def test_long_excerpt_is_rejected() -> None:
    evidence = Evidence(
        citation="Doc", url="https://example.org/x", excerpt="a" * (MAX_EXCERPT_CHARS + 1)
    )
    assert any("limit" in problem for problem in evidence.errors())


def test_resolution_requires_binary_outcome() -> None:
    problems = resolution_errors(2, Evidence(citation="Doc", url="https://x"), CREATED)
    assert any("outcome" in problem for problem in problems)


def test_schema_file_matches_the_model() -> None:
    schema = json.loads(
        (Path(__file__).resolve().parents[1] / "schema" / "entry.schema.json").read_text(
            encoding="utf-8"
        )
    )
    common = set(make(kind="point", interval=None, point=0.5).to_dict()) - {"p"}
    assert set(schema["required"]) == common
    assert schema["properties"]["criteria"]["minLength"] == 10
