"""Scoring: closed-form CRPS over the declared interval, with Brier and Murphy as diagnostics.

The interval is the unit of forecast. A point forecast is the degenerate interval [p, p], so both
kinds are scored on the same scale and can be compared without a special case.
"""

from __future__ import annotations

from typing import Any, Sequence

from .model import Entry, parse_iso_date, utc_now

# Width buckets for the band table (lower bound inclusive, upper exclusive).
WIDTH_BUCKETS: tuple[tuple[str, float, float], ...] = (
    ("0.00-0.10", 0.0, 0.10),
    ("0.10-0.30", 0.10, 0.30),
    ("0.30-0.60", 0.30, 0.60),
    ("0.60-1.00", 0.60, 1.0000001),
)

HORIZON_BUCKETS: tuple[tuple[str, int, int], ...] = (
    ("<=30d", 0, 30),
    ("31-90d", 31, 90),
    ("91-365d", 91, 365),
    (">365d", 366, 10**6),
)


def crps(low: float, high: float, outcome: int) -> float:
    """CRPS of the uniform distribution on [low, high] against a binary outcome.

    Closed form, with the tail terms that a naive derivation drops: when the outcome lies outside
    the interval the CDF is saturated and the indicator only flips at the outcome, leaving a slab
    of length |outcome - bound| where the integrand equals 1.
    """
    if not 0.0 <= low <= high <= 1.0:
        raise ValueError(f"invalid interval [{low}, {high}]")
    y = float(outcome)
    if not 0.0 <= y <= 1.0:
        raise ValueError(f"invalid outcome {outcome!r}")
    if high == low:
        return abs(low - y)
    if y <= low:
        return (high - low) / 3.0 + (low - y)
    if y >= high:
        return (high - low) / 3.0 + (y - high)
    return ((y - low) ** 3 + (high - y) ** 3) / (3.0 * (high - low) ** 2)


def score_entry(entry: Entry, outcome: int) -> dict[str, Any]:
    low, high = entry.interval
    midpoint = entry.midpoint
    return {
        "id": entry.id,
        "crps": crps(low, high, outcome),
        "brier": (midpoint - outcome) ** 2,
        "width": entry.width,
        "midpoint": midpoint,
    }


def murphy(pairs: Sequence[tuple[float, int]], bins: int = 10) -> dict[str, Any] | None:
    """Murphy decomposition of the Brier score over binned forecasts.

    The identity is exact for the binned forecast (`bs_binned`), which is what reliability,
    resolution and uncertainty decompose; the raw mean Brier is reported next to it so the
    difference is visible instead of hidden.
    """
    total = len(pairs)
    if total == 0:
        return None
    base = sum(outcome for _, outcome in pairs) / total
    reliability = 0.0
    resolution = 0.0
    detail: list[dict[str, Any]] = []
    bs_binned = 0.0
    for index in range(bins):
        low = index / bins
        high = (index + 1) / bins
        members = [
            (forecast, outcome)
            for forecast, outcome in pairs
            if low <= forecast < high or (index == bins - 1 and forecast == 1.0)
        ]
        if not members:
            continue
        count = len(members)
        mean_forecast = sum(forecast for forecast, _ in members) / count
        mean_outcome = sum(outcome for _, outcome in members) / count
        reliability += count * (mean_forecast - mean_outcome) ** 2
        resolution += count * (mean_outcome - base) ** 2
        bs_binned += sum((mean_forecast - outcome) ** 2 for _, outcome in members)
        detail.append(
            {
                "bin": f"{low:.1f}-{high:.1f}",
                "n": count,
                "forecast": round(mean_forecast, 6),
                "observed": round(mean_outcome, 6),
            }
        )
    reliability /= total
    resolution /= total
    uncertainty = base * (1.0 - base)
    bs_binned /= total
    raw_brier = sum((forecast - outcome) ** 2 for forecast, outcome in pairs) / total
    return {
        "n": total,
        "bins": detail,
        "reliability": reliability,
        "resolution": resolution,
        "uncertainty": uncertainty,
        "bs_binned": bs_binned,
        "bs_raw": raw_brier,
        "identity_residual": bs_binned - (reliability - resolution + uncertainty),
    }


def summarize(
    state: dict[str, dict[str, Any]], minimum_sample: int = 20, as_of: str | None = None
) -> dict[str, Any]:
    """Aggregate the ledger into the numbers the report prints.

    For a binary outcome a probability band cannot "contain" the outcome (0 and 1 sit outside any
    [0.6, 0.9]), so there is no per-entry coverage to count. What is meaningful is the observed
    frequency of the outcomes grouped by declared width, compared with the average declared band:
    that is what `bands` reports.
    """
    resolved: list[dict[str, Any]] = []
    for entry_id in sorted(state):
        record = state[entry_id]
        if record["status"] != "resolved":
            continue
        entry: Entry = record["entry"]
        outcome = int((record["resolution"] or {}).get("outcome", 0))
        low, high = entry.interval
        row = score_entry(entry, outcome)
        row.update(
            {
                "question": entry.question,
                "interval": entry.as_forecast(),
                "due": entry.due,
                "horizon_days": entry.horizon_days,
                "low": low,
                "high": high,
                "outcome": outcome,
            }
        )
        resolved.append(row)

    counts = {
        "entries": len(state),
        "draft": sum(1 for r in state.values() if r["status"] == "draft"),
        "open": sum(1 for r in state.values() if r["status"] == "open"),
        "resolved": len(resolved),
        "void": sum(1 for r in state.values() if r["status"] == "void"),
    }
    n = len(resolved)
    sufficient = n >= minimum_sample

    summary: dict[str, Any] = {
        "counts": counts,
        "sufficient": sufficient,
        "minimum_sample": minimum_sample,
        "resolved": resolved,
        "crps_mean": (sum(row["crps"] for row in resolved) / n) if n else None,
        "brier_mean": (sum(row["brier"] for row in resolved) / n) if n else None,
        "sharpness": (sum(row["width"] for row in resolved) / n) if n else None,
        "base_rate": (sum(row["outcome"] for row in resolved) / n) if n else None,
        "murphy": murphy([(row["midpoint"], row["outcome"]) for row in resolved]),
        "windows": {},
        "bands": [],
        "hygiene": {},
    }

    for name, low, high in WIDTH_BUCKETS:
        members = [row for row in resolved if low <= row["width"] < high]
        if members:
            mean_low = sum(row["low"] for row in members) / len(members)
            mean_high = sum(row["high"] for row in members) / len(members)
            observed = sum(row["outcome"] for row in members) / len(members)
            outside = not (mean_low <= observed <= mean_high)
        else:
            mean_low = mean_high = observed = None
            outside = None
        summary["bands"].append(
            {
                "bucket": name,
                "n": len(members),
                "mean_low": mean_low,
                "mean_high": mean_high,
                "observed": observed,
                "outside": outside,
                "insufficient": bool(members) and len(members) < 5,
            }
        )

    horizon: dict[str, dict[str, Any]] = {}
    for name, low, high in HORIZON_BUCKETS:
        members = [row for row in resolved if low <= row["horizon_days"] <= high]
        horizon[name] = {
            "n": len(members),
            "crps": (sum(row["crps"] for row in members) / len(members)) if members else None,
            "brier": (sum(row["brier"] for row in members) / len(members)) if members else None,
            "base_rate": (
                (sum(row["outcome"] for row in members) / len(members)) if members else None
            ),
        }
    summary["windows"]["horizon"] = horizon

    quarters: dict[str, dict[str, Any]] = {}
    for row in resolved:
        year, month = int(row["due"][:4]), int(row["due"][5:7])
        key = f"{year}-Q{(month - 1) // 3 + 1}"
        bucket = quarters.setdefault(key, {"n": 0, "crps": 0.0, "outcomes": 0})
        bucket["n"] += 1
        bucket["crps"] += row["crps"]
        bucket["outcomes"] += row["outcome"]
    for bucket in quarters.values():
        bucket["crps"] /= bucket["n"]
        bucket["base_rate"] = bucket["outcomes"] / bucket["n"]
        del bucket["outcomes"]
    summary["windows"]["quarter"] = dict(sorted(quarters.items()))

    today = parse_iso_date(as_of or utc_now()[:10], "as_of")
    overdue = [
        entry_id
        for entry_id, record in state.items()
        if record["status"] == "open" and parse_iso_date(record["entry"].due, "due") < today
    ]
    summary["hygiene"] = {
        "void_rate": (counts["void"] / counts["entries"]) if counts["entries"] else 0.0,
        "overdue_open": len(overdue),
        "without_origin": sum(1 for record in state.values() if not record["entry"].origin),
    }
    return summary
