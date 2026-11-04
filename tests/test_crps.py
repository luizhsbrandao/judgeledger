"""CRPS: closed form, checked against numerical integration and properties."""

from __future__ import annotations

import pytest

from judgeledger.scoring import crps


def simpson(function, a: float, b: float, steps: int = 2000) -> float:
    """Composite Simpson with endpoint values taken from the interior of the segment.

    The integrand jumps at the outcome (and at the interval bounds), so evaluating exactly at a
    breakpoint would pick the wrong side and introduce an O(h) error. The interior limits are the
    correct ones inside each segment.
    """
    if steps % 2:
        steps += 1
    h = (b - a) / steps
    epsilon = 1e-12
    total = function(a + epsilon) + function(b - epsilon)
    for index in range(1, steps):
        total += (4 if index % 2 else 2) * function(a + index * h)
    return total * h / 3


def crps_numeric(low: float, high: float, outcome: int) -> float:
    """Integrate (F(x) - 1{x >= y})^2 over [0,1], splitting at every kink."""

    def cdf(x: float) -> float:
        if high == low:
            return 0.0 if x < low else 1.0
        if x < low:
            return 0.0
        if x > high:
            return 1.0
        return (x - low) / (high - low)

    def integrand(x: float) -> float:
        return (cdf(x) - (1.0 if x >= outcome else 0.0)) ** 2

    points = sorted({0.0, 1.0, float(low), float(high), float(outcome)})
    total = 0.0
    for left, right in zip(points, points[1:]):
        if right > left:
            total += simpson(integrand, left, right)
    return total


@pytest.mark.parametrize(
    ("low", "high", "outcome"),
    [
        (0.2, 0.8, 1),
        (0.2, 0.8, 0),
        (0.2, 0.8, 0.5),
        (0.2, 0.8, 0.3),
        (0.6, 0.95, 1),
        (0.0, 1.0, 1),
        (0.0, 1.0, 0),
        (0.75, 0.75, 0),
        (0.35, 0.55, 1),
    ],
)
def test_closed_form_matches_integration(low: float, high: float, outcome: int) -> None:
    assert crps(low, high, outcome) == pytest.approx(
        crps_numeric(low, high, outcome), abs=1e-10
    )


def test_degenerate_interval_is_absolute_error() -> None:
    for probability in (0.0, 0.2, 0.5, 0.73, 1.0):
        assert crps(probability, probability, 0) == pytest.approx(probability)
        assert crps(probability, probability, 1) == pytest.approx(1 - probability)


def test_full_interval_is_the_worst_sharp_forecast() -> None:
    assert crps(0.0, 1.0, 0) == pytest.approx(1 / 3)
    assert crps(0.0, 1.0, 1) == pytest.approx(1 / 3)


def test_missing_tail_term_is_wrong_outside_the_interval() -> None:
    """The naive derivation (width/3 everywhere outside) understates the cost by the tail."""

    naive = (0.8 - 0.2) / 3
    assert crps(0.2, 0.8, 1) == pytest.approx(naive + (1.0 - 0.8))
    assert crps(0.2, 0.8, 1) > naive


def test_symmetry() -> None:
    assert crps(0.2, 0.8, 1) == pytest.approx(crps(0.2, 0.8, 0))

def test_wider_interval_costs_more_when_the_outcome_is_inside() -> None:
    narrow = crps(0.0, 0.4, 0)
    wide = crps(0.0, 0.8, 0)
    assert narrow < wide
    assert wide == pytest.approx((0.8 - 0.0) / 3)


def test_an_interval_that_covers_the_outcome_beats_a_confident_miss() -> None:
    assert crps(0.0, 0.4, 0) < crps(0.9, 0.9, 0)


def test_invalid_interval_is_rejected() -> None:
    with pytest.raises(ValueError):
        crps(0.8, 0.2, 1)
    with pytest.raises(ValueError):
        crps(-0.1, 0.5, 1)


def test_invalid_outcome_is_rejected() -> None:
    with pytest.raises(ValueError):
        crps(0.2, 0.8, 2)


def expected_absolute_error(low: float, high: float, outcome: int) -> float:
    """E|X - y| for X ~ U[low, high], computed independently of the closed form."""
    mean = (low + high) / 2
    if outcome <= low:
        return mean - outcome
    if outcome >= high:
        return outcome - mean
    return ((outcome - low) ** 2 + (high - outcome) ** 2) / (2 * (high - low))


@pytest.mark.parametrize(
    ("low", "high", "outcome"),
    [(0.2, 0.8, 1), (0.2, 0.8, 0), (0.3, 0.9, 1), (0.0, 1.0, 0), (0.4, 0.6, 1), (0.1, 0.2, 0)],
)
def test_matches_the_expectation_identity(low: float, high: float, outcome: int) -> None:
    """CRPS(F, y) = E|X - y| - ½E|X - X'|, and ½E|X - X'| = (u - l)/6 for a uniform."""
    expected = expected_absolute_error(low, high, outcome) - (high - low) / 6
    assert crps(low, high, outcome) == pytest.approx(expected, abs=1e-12)
