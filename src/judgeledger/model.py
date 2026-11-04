"""Data model and validation for judgeledger.

The model knows nothing about storage, scoring or the CLI: it declares the entities and the
integrity rules that make a judgment auditable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

SCHEMA_VERSION = 1
ID_RE = re.compile(r"^E\d{3,}$")
STATUSES = ("draft", "open", "resolved", "void")
KINDS = ("point", "interval")
MIN_CRITERIA_CHARS = 10
MAX_EXCERPT_CHARS = 500


class IntegrityError(Exception):
    """A rule of the ledger was violated. The CLI maps this to exit code 2."""


def utc_now() -> str:
    """Timestamp in UTC, second precision, stable textual form."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso_date(value: str, field_name: str = "date") -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise IntegrityError(f"{field_name}: expected YYYY-MM-DD, got {value!r}") from exc


def parse_ts(value: str, field_name: str = "timestamp") -> datetime:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise IntegrityError(f"{field_name}: expected ISO-8601, got {value!r}") from exc


def check_probability(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise IntegrityError(f"{name}: expected a number in [0,1], got {value!r}") from exc
    if not 0.0 <= number <= 1.0:
        raise IntegrityError(f"{name}: {number} is outside [0,1]")
    return number


@dataclass
class Evidence:
    """Where a resolution comes from. A resolution without a locator is not a resolution."""

    citation: str = ""
    url: str = ""
    archive_url: str = ""
    excerpt: str = ""

    def locators(self) -> list[str]:
        return [loc for loc in (self.url, self.archive_url) if loc.strip()]

    def has_locator(self) -> bool:
        return bool(self.locators())

    def to_dict(self) -> dict[str, str]:
        return {
            "citation": self.citation,
            "url": self.url,
            "archive_url": self.archive_url,
            "excerpt": self.excerpt,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Evidence":
        data = data or {}
        return cls(
            citation=str(data.get("citation", "")),
            url=str(data.get("url", "")),
            archive_url=str(data.get("archive_url", "")),
            excerpt=str(data.get("excerpt", "")),
        )

    def errors(self) -> list[str]:
        problems: list[str] = []
        if not self.citation.strip():
            problems.append("evidence: citation is required")
        if not self.has_locator():
            problems.append("evidence: url or archive_url is required")
        if len(self.excerpt) > MAX_EXCERPT_CHARS:
            problems.append(
                f"evidence: excerpt is {len(self.excerpt)} chars, limit is {MAX_EXCERPT_CHARS}"
            )
        return problems


@dataclass
class Entry:
    """One judgment, immutable from creation."""

    id: str
    question: str
    criteria: str
    due: str
    kind: str
    created_at: str
    actor: str
    horizon_days: int
    p: float | None = None
    l: float | None = None
    u: float | None = None
    tags: list[str] = field(default_factory=list)
    origin: str | None = None
    schema_version: int = SCHEMA_VERSION

    # -- derived -----------------------------------------------------------
    @property
    def interval(self) -> tuple[float, float]:
        if self.kind == "point":
            assert self.p is not None
            return (self.p, self.p)
        assert self.l is not None and self.u is not None
        return (self.l, self.u)

    @property
    def midpoint(self) -> float:
        low, high = self.interval
        return (low + high) / 2.0

    @property
    def width(self) -> float:
        low, high = self.interval
        return high - low

    def as_forecast(self) -> str:
        low, high = self.interval
        if self.kind == "point":
            return f"{self.p:.2f}"
        return f"[{low:.2f}, {high:.2f}]"

    # -- serialisation -----------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "question": self.question,
            "criteria": self.criteria,
            "due": self.due,
            "kind": self.kind,
            "created_at": self.created_at,
            "actor": self.actor,
            "horizon_days": self.horizon_days,
            "tags": list(self.tags),
            "origin": self.origin,
            "schema_version": self.schema_version,
        }
        if self.kind == "point":
            data["p"] = self.p
        else:
            data["l"] = self.l
            data["u"] = self.u
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Entry":
        if not isinstance(data, dict):
            raise IntegrityError(f"entry: expected an object, got {type(data).__name__}")
        kind = str(data.get("kind", ""))
        if kind not in KINDS:
            raise IntegrityError(f"entry {data.get('id')!r}: kind must be one of {KINDS}")
        horizon = data.get("horizon_days", 0)
        try:
            horizon_int = int(horizon)
        except (TypeError, ValueError) as exc:
            raise IntegrityError(f"entry {data.get('id')!r}: horizon_days must be an integer") from exc
        raw_tags = data.get("tags") or []
        if not isinstance(raw_tags, list) or any(not isinstance(t, str) for t in raw_tags):
            raise IntegrityError(f"entry {data.get('id')!r}: tags must be a list of strings")
        origin = data.get("origin")
        if origin is not None and not isinstance(origin, str):
            raise IntegrityError(f"entry {data.get('id')!r}: origin must be a string or null")
        return cls(
            id=str(data.get("id", "")),
            question=str(data.get("question", "")),
            criteria=str(data.get("criteria", "")),
            due=str(data.get("due", "")),
            kind=kind,
            created_at=str(data.get("created_at", "")),
            actor=str(data.get("actor", "")),
            horizon_days=horizon_int,
            p=data.get("p"),
            l=data.get("l"),
            u=data.get("u"),
            tags=list(raw_tags),
            origin=origin,
            schema_version=int(data.get("schema_version", SCHEMA_VERSION)),
        )

    # -- validation --------------------------------------------------------
    def errors(self) -> list[str]:
        """All integrity problems in this entry, as human-readable lines."""
        problems: list[str] = []
        if not ID_RE.match(self.id):
            problems.append(f"entry {self.id!r}: id must match E<digits>, e.g. E001")
        if not self.question.strip():
            problems.append(f"entry {self.id}: question is empty")
        if len(self.criteria.strip()) < MIN_CRITERIA_CHARS:
            problems.append(
                f"entry {self.id}: resolution criteria must have at least "
                f"{MIN_CRITERIA_CHARS} non-space characters"
            )
        try:
            due = parse_iso_date(self.due, f"entry {self.id}: due")
        except IntegrityError as exc:
            problems.append(str(exc))
            due = None
        try:
            created = parse_ts(self.created_at, f"entry {self.id}: created_at").date()
        except IntegrityError as exc:
            problems.append(str(exc))
            created = None
        if due is not None and created is not None and due <= created:
            problems.append(
                f"entry {self.id}: due ({self.due}) must be after created_at "
                f"({self.created_at}); a judgment cannot be backdated"
            )
        if self.horizon_days < 0:
            problems.append(f"entry {self.id}: horizon_days is negative")

        try:
            if self.kind == "point":
                check_probability(self.p, f"entry {self.id}: p")
            elif self.kind == "interval":
                low = check_probability(self.l, f"entry {self.id}: l")
                high = check_probability(self.u, f"entry {self.id}: u")
                if low >= high:
                    problems.append(
                        f"entry {self.id}: interval lower bound ({low}) must be below upper ({high})"
                    )
        except IntegrityError as exc:
            problems.append(str(exc))

        if not self.actor.strip():
            problems.append(f"entry {self.id}: actor is empty")
        if self.schema_version != SCHEMA_VERSION:
            problems.append(
                f"entry {self.id}: schema_version {self.schema_version} != {SCHEMA_VERSION}"
            )
        return problems


def build_entry(
    *,
    entry_id: str,
    question: str,
    criteria: str,
    due: str,
    kind: str,
    actor: str,
    created_at: str,
    point: float | None = None,
    interval: tuple[float, float] | None = None,
    tags: list[str] | None = None,
    origin: str | None = None,
) -> Entry:
    """Construct an entry, rejecting anything that violates the rules."""
    if kind == "point" and interval is not None:
        raise IntegrityError("forecast: pass either --point or --interval, not both")
    if kind == "interval" and point is not None:
        raise IntegrityError("forecast: pass either --point or --interval, not both")
    created = parse_ts(created_at, "created_at")
    due_date = parse_iso_date(due, "due")
    created_date = created.date()
    if due_date <= created_date:
        raise IntegrityError(
            f"due ({due}) must be after creation date ({created_date.isoformat()}); "
            "a judgment cannot be backdated"
        )
    entry = Entry(
        id=entry_id,
        question=question,
        criteria=criteria,
        due=due,
        kind=kind,
        created_at=created_at,
        actor=actor,
        horizon_days=(due_date - created_date).days,
        p=point if kind == "point" else None,
        l=interval[0] if interval and kind == "interval" else None,
        u=interval[1] if interval and kind == "interval" else None,
        tags=list(tags or []),
        origin=origin,
    )
    problems = entry.errors()
    if problems:
        raise IntegrityError("; ".join(problems))
    return entry


def resolution_errors(outcome: Any, evidence: Evidence, resolved_at: str) -> list[str]:
    problems: list[str] = []
    if outcome not in (0, 1, False, True):
        problems.append(f"resolution: outcome must be 0 or 1, got {outcome!r}")
    try:
        parse_ts(resolved_at, "resolution.resolved_at")
    except IntegrityError as exc:
        problems.append(str(exc))
    problems.extend(evidence.errors())
    return problems
