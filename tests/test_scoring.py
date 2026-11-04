"""Aggregation: counts, coverage, sharpness, Murphy, windows, insufficient sample."""

from __future__ import annotations

import pytest

from judgeledger.scoring import crps, summarize
from helpers import add, seed


def test_counts_and_statuses(ledger) -> None:
    seed(ledger, 3)
    add(ledger, outcome=None)
    summary = summarize(ledger.state())
    assert summary["counts"] == {
        "entries": 4,
        "draft": 0,
        "open": 1,
        "resolved": 3,
        "void": 0,
    }


def test_void_is_not_counted_as_error(ledger) -> None:
    entry = add(ledger, outcome=None)
    ledger.void(entry.id, reason="ambiguous criterion", resolver="tester")
    summary = summarize(ledger.state())
    assert summary["counts"]["void"] == 1
    assert summary["counts"]["resolved"] == 0
    assert summary["crps_mean"] is None


def test_bands_compare_observed_frequency_with_the_declared_band(ledger) -> None:
    add(ledger, interval=(0.6, 0.9), outcome=1)
    add(ledger, interval=(0.6, 0.9), outcome=1)
    add(ledger, interval=(0.6, 0.9), outcome=0)
    band = summarize(ledger.state())["bands"][2]
    assert band["bucket"] == "0.30-0.60"
    assert band["n"] == 3
    assert band["observed"] == pytest.approx(2 / 3)
    assert band["outside"] is False
    assert band["insufficient"] is True


def test_band_outside_is_flagged_when_the_frequency_leaves_it(ledger) -> None:
    for _ in range(3):
        add(ledger, interval=(0.8, 0.95), outcome=0)
    band = summarize(ledger.state())["bands"][1]
    assert band["bucket"] == "0.10-0.30"
    assert band["observed"] == 0.0
    assert band["outside"] is True


def test_mean_crps_is_the_mean_of_the_entries(ledger) -> None:
    add(ledger, interval=(0.2, 0.8), outcome=1)
    add(ledger, point=0.3, outcome=0)
    summary = summarize(ledger.state())
    expected = (crps(0.2, 0.8, 1) + crps(0.3, 0.3, 0)) / 2
    assert summary["crps_mean"] == pytest.approx(expected)


def test_murphy_identity_holds_for_the_binned_forecast(ledger) -> None:
    seed(ledger, 20)
    summary = summarize(ledger.state())
    murphy = summary["murphy"]
    assert murphy["identity_residual"] == pytest.approx(0.0, abs=1e-12)
    assert 0.0 <= murphy["reliability"] <= 1.0


def test_horizon_buckets(ledger) -> None:
    for due in ("2026-01-20", "2026-02-28", "2026-06-30", "2027-12-31"):
        add(ledger, due=due, outcome=1)
    horizon = summarize(ledger.state())["windows"]["horizon"]
    assert horizon["<=30d"]["n"] == 1
    assert horizon["31-90d"]["n"] == 1
    assert horizon["91-365d"]["n"] == 1
    assert horizon[">365d"]["n"] == 1


def test_quarter_buckets(ledger) -> None:
    add(ledger, due="2026-01-20", outcome=1)
    add(ledger, due="2026-06-30", outcome=0)
    add(ledger, due="2026-06-30", outcome=1)
    quarters = summarize(ledger.state())["windows"]["quarter"]
    assert quarters["2026-Q1"]["n"] == 1
    assert quarters["2026-Q2"]["n"] == 2


def test_insufficient_sample_is_flagged(ledger) -> None:
    seed(ledger, 7)
    summary = summarize(ledger.state(), minimum_sample=20)
    assert summary["sufficient"] is False
    assert summary["counts"]["resolved"] == 7


def test_thin_bands_are_marked_insufficient(ledger) -> None:
    seed(ledger, 4)
    bands = summarize(ledger.state(), minimum_sample=2)["bands"]
    populated = [row for row in bands if row["n"]]
    assert populated
    assert any(row["insufficient"] for row in populated)


def test_hygiene_counts_overdue_and_origin(ledger) -> None:
    entry = ledger.add(
        question="Late?",
        criteria="Stated in the official published record",
        due="2026-02-01",
        kind="point",
        actor="tester",
        point=0.5,
        created_at="2026-01-01T12:00:00Z",
    )
    ledger.open_entry(entry.id, "tester")
    summary = summarize(ledger.state(), as_of="2026-03-01")
    assert summary["hygiene"]["overdue_open"] == 1
    assert summary["hygiene"]["without_origin"] == 1
    assert summary["hygiene"]["void_rate"] == 0.0
