"""Deterministic Markdown report.

Nothing in here reads the clock: the report is a function of the ledger and the `as_of` date, so
the same inputs produce byte-identical output and a stable digest.
"""

from __future__ import annotations

import hashlib
from typing import Any

from .model import utc_now
from .scoring import summarize


def _number(value: float | None, digits: int = 4) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def _percent(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def _cell(text: Any, limit: int = 64) -> str:
    collapsed = " ".join(str(text).split())
    if len(collapsed) > limit:
        collapsed = collapsed[: limit - 1] + "…"
    return collapsed.replace("|", "\\|")


def build(state: dict[str, dict[str, Any]], *, minimum_sample: int = 20, as_of: str | None = None) -> str:
    """Render the report. `as_of` is an input, not a timestamp of generation."""
    as_of_date = as_of or utc_now()[:10]
    summary = summarize(state, minimum_sample, as_of_date)
    counts = summary["counts"]
    resolved = summary["resolved"]

    lines: list[str] = []
    lines.append("# judgeledger report")
    lines.append("")
    lines.append(
        f"{counts['entries']} entries · {counts['resolved']} resolved · {counts['open']} open · "
        f"{counts['draft']} draft · {counts['void']} void · as of {as_of_date}"
    )
    lines.append("")

    if not resolved:
        lines.append("> **NO RESOLVED JUDGMENTS — nothing to score yet.**")
        lines.append("")
        return "\n".join(lines)

    lines.append("## Scores")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| CRPS (mean, lower is better) | {_number(summary['crps_mean'])} |")
    lines.append(f"| Brier at midpoint (mean, secondary) | {_number(summary['brier_mean'])} |")
    lines.append(f"| Sharpness (mean interval width) | {_number(summary['sharpness'])} |")
    lines.append(f"| Observed base rate | {_percent(summary['base_rate'])} |")
    lines.append("")

    if not summary["sufficient"]:
        lines.append(
            f"> **INSUFFICIENT SAMPLE — {counts['resolved']} resolved judgments; "
            f"the minimum is {minimum_sample}.**"
        )
        lines.append("> The calibration curve and the Murphy decomposition are not reported.")
        lines.append("")

    murphy = summary["murphy"]
    if summary["sufficient"] and murphy:
        lines.append("## Calibration (midpoints, 10 bins)")
        lines.append("")
        lines.append("| Bin | n | Mean forecast | Observed frequency |")
        lines.append("|---|---|---|---|")
        thin: list[str] = []
        for row in murphy["bins"]:
            mark = ""
            if row["n"] < 5:
                mark = " †"
                thin.append(row["bin"])
            lines.append(
                f"| {row['bin']} | {row['n']}{mark} | "
                f"{_number(row['forecast'], 3)} | {_number(row['observed'], 3)} |"
            )
        lines.append("")
        if thin:
            lines.append(
                f"† fewer than 5 judgments in the bin ({', '.join(thin)}); "
                "read as indicative only."
            )
            lines.append("")

        lines.append("## Murphy decomposition")
        lines.append("")
        lines.append("| Reliability | Resolution | Uncertainty | BS (binned) | Identity residual |")
        lines.append("|---|---|---|---|---|")
        lines.append(
            f"| {_number(murphy['reliability'])} | {_number(murphy['resolution'])} | "
            f"{_number(murphy['uncertainty'])} | {_number(murphy['bs_binned'])} | "
            f"{murphy['identity_residual']:.2e} |"
        )
        lines.append("")
        lines.append(
            f"BS = REL − RES + UNC holds exactly for the binned forecast; raw mean Brier is "
            f"{_number(murphy['bs_raw'])}."
        )
        lines.append("")

    lines.append("## Declared bands vs observed frequency")
    lines.append("")
    lines.append("| Width | n | Mean declared band | Observed frequency | Verdict |")
    lines.append("|---|---|---|---|---|")
    for row in summary["bands"]:
        if not row["n"]:
            lines.append(f"| {row['bucket']} | 0 | — | — | — |")
            continue
        band = f"[{_number(row['mean_low'], 3)}, {_number(row['mean_high'], 3)}]"
        if row["insufficient"]:
            verdict = "insufficient (n<5)"
        elif row["outside"]:
            verdict = "**outside**"
        else:
            verdict = "inside"
        lines.append(
            f"| {row['bucket']} | {row['n']} | {band} | "
            f"{_percent(row['observed'])} | {verdict} |"
        )
    lines.append("")
    lines.append(
        "A binary outcome cannot fall inside a probability band, so the check is at group level: "
        "the observed frequency of the outcomes in a width bucket against the average band "
        "declared there."
    )
    lines.append("")

    lines.append("## By horizon")
    lines.append("")
    lines.append("| Horizon | n | CRPS | Brier | Base rate |")
    lines.append("|---|---|---|---|---|")
    for name, row in summary["windows"]["horizon"].items():
        lines.append(
            f"| {name} | {row['n']} | {_number(row['crps'])} | {_number(row['brier'])} | "
            f"{_percent(row['base_rate'])} |"
        )
    lines.append("")

    lines.append("## By quarter (due date)")
    lines.append("")
    lines.append("| Quarter | n | CRPS | Base rate |")
    lines.append("|---|---|---|---|")
    for name, row in summary["windows"]["quarter"].items():
        lines.append(
            f"| {name} | {row['n']} | {_number(row['crps'])} | {_percent(row['base_rate'])} |"
        )
    lines.append("")

    hygiene = summary["hygiene"]
    lines.append("## Hygiene")
    lines.append("")
    lines.append("| Indicator | Value |")
    lines.append("|---|---|")
    lines.append(f"| Void rate | {_percent(hygiene['void_rate'])} |")
    lines.append(f"| Open past the due date | {hygiene['overdue_open']} |")
    lines.append(f"| Without origin tag | {hygiene['without_origin']} |")
    lines.append("")

    lines.append("## Resolved judgments")
    lines.append("")
    lines.append("| id | Question | Interval | Outcome | CRPS | Brier | Late |")
    lines.append("|---|---|---|---|---|---|---|")
    for row in resolved:
        record = state[row["id"]]
        resolution = record["resolution"] or {}
        outcome = int(resolution.get("outcome", 0))
        late = "yes" if resolution.get("late") else ""
        lines.append(
            f"| {row['id']} | {_cell(row['question'])} | {row['interval']} | {outcome} | "
            f"{_number(row['crps'])} | {_number(row['brier'])} | {late} |"
        )
    lines.append("")

    lines.append("## Sources")
    lines.append("")
    for row in resolved:
        resolution = state[row["id"]]["resolution"] or {}
        evidence = resolution.get("evidence") or {}
        locator = evidence.get("archive_url") or evidence.get("url") or ""
        citation = evidence.get("citation", "")
        lines.append(f"- **{row['id']}** — {_cell(citation, 120)} — {locator}")
    lines.append("")
    lines.append(
        "Method: CRPS of the uniform distribution over the declared interval (a point forecast is "
        "the degenerate interval) ranks the judgments; the Brier score at the midpoint is reported, "
        "never ranked. See `docs/pontuacao.md` for the formulas and a worked example."
    )
    lines.append("")
    return "\n".join(lines)


def digest(markdown: str) -> str:
    return hashlib.sha256(markdown.encode("utf-8")).hexdigest()
