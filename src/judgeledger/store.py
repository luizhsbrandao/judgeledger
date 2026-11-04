"""Storage: an append-only ledger plus a hash-chained event log.

`ledger.jsonl` holds one canonical JSON object per entry and is never rewritten.
`events.jsonl` is the source of truth for state: every action is appended with the digest of the
previous event, so an edit anywhere breaks the chain. `validate` compares both files.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .model import (
    Entry,
    Evidence,
    IntegrityError,
    build_entry,
    parse_iso_date,
    resolution_errors,
    utc_now,
)

LEDGER_FILE = "ledger.jsonl"
EVENTS_FILE = "events.jsonl"
LOCK_FILE = ".lock"
GENESIS = "0" * 64


def canonical(obj: Any) -> bytes:
    """Stable JSON encoding: same object -> same bytes, on any platform."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def event_digest(event: dict[str, Any]) -> str:
    payload = {key: value for key, value in event.items() if key != "hash"}
    return "sha256:" + sha256_hex(canonical(payload))


class Ledger:
    """A ledger directory: `ledger.jsonl`, `events.jsonl` and a `.lock`."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)
        self.ledger_path = self.root / LEDGER_FILE
        self.events_path = self.root / EVENTS_FILE
        self.lock_path = self.root / LOCK_FILE

    # -- lifecycle ---------------------------------------------------------
    @classmethod
    def init(cls, root: str | os.PathLike[str], actor: str, ts: str | None = None) -> "Ledger":
        ledger = cls(root)
        ledger.root.mkdir(parents=True, exist_ok=True)
        if ledger.ledger_path.exists() or ledger.events_path.exists():
            raise IntegrityError(f"{ledger.root}: ledger already initialised")
        if not actor.strip():
            raise IntegrityError("init: actor is required")
        ledger.ledger_path.write_text("", encoding="utf-8")
        ledger.events_path.write_text("", encoding="utf-8")
        ledger._append_event(
            action="init",
            entry_id="",
            payload={"actor": actor, "schema_version": 1},
            actor=actor,
            ts=ts,
        )
        return ledger

    def exists(self) -> bool:
        return self.ledger_path.is_file() and self.events_path.is_file()

    def require(self) -> None:
        if not self.exists():
            raise IntegrityError(
                f"{self.root}: no ledger here (expected {LEDGER_FILE} and {EVENTS_FILE})"
            )

    # -- low-level io ------------------------------------------------------
    @contextmanager
    def _exclusive(self) -> Iterator[None]:
        self.root.mkdir(parents=True, exist_ok=True)
        with open(self.lock_path, "w", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _append_line(self, path: Path, obj: Any) -> None:
        line = canonical(obj) + b"\n"
        with open(path, "ab") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())

    def _append_event(
        self,
        *,
        action: str,
        entry_id: str,
        payload: dict[str, Any],
        actor: str,
        ts: str | None = None,
    ) -> dict[str, Any]:
        events = self._read_events()
        previous = events[-1]["hash"] if events else GENESIS
        event: dict[str, Any] = {
            "seq": len(events) + 1,
            "ts": ts or utc_now(),
            "actor": actor,
            "action": action,
            "entry": entry_id,
            "payload": payload,
            "prev_hash": previous,
        }
        event["hash"] = event_digest(event)
        self._append_line(self.events_path, event)
        return event

    def _read_jsonl(self, path: Path, label: str) -> list[dict[str, Any]]:
        objects: list[dict[str, Any]] = []
        if not path.is_file():
            return objects
        with open(path, "r", encoding="utf-8") as handle:
            for number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise IntegrityError(f"{label} line {number}: invalid JSON ({exc.msg})") from exc
                if not isinstance(value, dict):
                    raise IntegrityError(f"{label} line {number}: expected a JSON object")
                objects.append(value)
        return objects

    def _read_events(self) -> list[dict[str, Any]]:
        return self._read_jsonl(self.events_path, EVENTS_FILE)

    # -- reads -------------------------------------------------------------
    def entries(self) -> list[Entry]:
        raw = self._read_jsonl(self.ledger_path, LEDGER_FILE)
        entries: list[Entry] = []
        seen: set[str] = set()
        for number, item in enumerate(raw, start=1):
            try:
                entry = Entry.from_dict(item)
            except IntegrityError as exc:
                raise IntegrityError(f"{LEDGER_FILE} line {number}: {exc}") from exc
            if entry.id in seen:
                raise IntegrityError(f"{LEDGER_FILE}: duplicate entry id {entry.id!r}")
            seen.add(entry.id)
            entries.append(entry)
        return entries

    def entries_by_id(self) -> dict[str, Entry]:
        return {entry.id: entry for entry in self.entries()}

    def events(self) -> list[dict[str, Any]]:
        return self._read_events()

    def next_id(self) -> str:
        entries = self.entries()
        numbers = [int(entry.id[1:]) for entry in entries if entry.id[1:].isdigit()]
        return f"E{max(numbers, default=0) + 1:03d}"

    # -- state -------------------------------------------------------------
    def state(self) -> dict[str, dict[str, Any]]:
        """Replay the event log into current state, or raise on an impossible transition."""
        current: dict[str, dict[str, Any]] = {}
        for entry in self.entries():
            current[entry.id] = {
                "entry": entry,
                "status": "draft",
                "resolution": None,
                "void": None,
            }
        for event in self._read_events():
            action = event.get("action")
            entry_id = event.get("entry", "")
            if action == "init":
                continue
            if entry_id not in current:
                raise IntegrityError(
                    f"{EVENTS_FILE} seq {event.get('seq')}: event for unknown entry {entry_id!r}"
                )
            record = current[entry_id]
            payload = event.get("payload") or {}
            if action == "create":
                if record["status"] != "draft":
                    raise IntegrityError(
                        f"{EVENTS_FILE} seq {event.get('seq')}: duplicate create for {entry_id}"
                    )
                continue
            if action == "open":
                if record["status"] != "draft":
                    raise IntegrityError(
                        f"{EVENTS_FILE} seq {event.get('seq')}: cannot open {entry_id} "
                        f"from status {record['status']}"
                    )
                record["status"] = "open"
                continue
            if action == "resolve":
                if record["status"] != "open":
                    raise IntegrityError(
                        f"{EVENTS_FILE} seq {event.get('seq')}: cannot resolve {entry_id} "
                        f"from status {record['status']}"
                    )
                record["status"] = "resolved"
                record["resolution"] = payload
                continue
            if action == "void":
                if record["status"] not in ("draft", "open"):
                    raise IntegrityError(
                        f"{EVENTS_FILE} seq {event.get('seq')}: cannot void {entry_id} "
                        f"from status {record['status']}"
                    )
                record["status"] = "void"
                record["void"] = payload
                continue
            raise IntegrityError(
                f"{EVENTS_FILE} seq {event.get('seq')}: unknown action {action!r}"
            )
        return current

    # -- writes ------------------------------------------------------------
    def add(
        self,
        *,
        question: str,
        criteria: str,
        due: str,
        kind: str,
        actor: str,
        point: float | None = None,
        interval: tuple[float, float] | None = None,
        tags: list[str] | None = None,
        origin: str | None = None,
        created_at: str | None = None,
    ) -> Entry:
        self.require()
        with self._exclusive():
            entry = build_entry(
                entry_id=self.next_id(),
                question=question,
                criteria=criteria,
                due=due,
                kind=kind,
                actor=actor,
                created_at=created_at or utc_now(),
                point=point,
                interval=interval,
                tags=tags,
                origin=origin,
            )
            snapshot = entry.to_dict()
            self._append_line(self.ledger_path, snapshot)
            self._append_event(
                action="create",
                entry_id=entry.id,
                payload={"entry": snapshot, "entry_hash": sha256_hex(canonical(snapshot))},
                actor=actor,
                ts=entry.created_at,
            )
        return entry

    def open_entry(self, entry_id: str, actor: str, ts: str | None = None) -> None:
        self.require()
        with self._exclusive():
            current = self.state()
            if entry_id not in current:
                raise IntegrityError(f"open: unknown entry {entry_id!r}")
            if current[entry_id]["status"] != "draft":
                raise IntegrityError(
                    f"open: {entry_id} is {current[entry_id]['status']}, only a draft can be opened"
                )
            self._append_event(action="open", entry_id=entry_id, payload={}, actor=actor, ts=ts)

    def resolve(
        self,
        entry_id: str,
        *,
        outcome: int,
        evidence: Evidence,
        resolver: str,
        resolved_at: str | None = None,
    ) -> dict[str, Any]:
        self.require()
        timestamp = resolved_at or utc_now()
        problems = resolution_errors(outcome, evidence, timestamp)
        if problems:
            raise IntegrityError("; ".join(problems))
        with self._exclusive():
            current = self.state()
            if entry_id not in current:
                raise IntegrityError(f"resolve: unknown entry {entry_id!r}")
            record = current[entry_id]
            if record["status"] != "open":
                raise IntegrityError(
                    f"resolve: {entry_id} is {record['status']}, only an open entry can be resolved"
                )
            entry: Entry = record["entry"]
            due = parse_iso_date(entry.due, f"entry {entry.id}: due")
            resolved_date = parse_iso_date(
                timestamp[:10], f"entry {entry.id}: resolved_at"
            )
            payload = {
                "outcome": int(outcome),
                "resolved_at": timestamp,
                "resolver": resolver,
                "evidence": evidence.to_dict(),
                "late": resolved_date > due,
            }
            self._append_event(
                action="resolve",
                entry_id=entry_id,
                payload=payload,
                actor=resolver,
                ts=timestamp,
            )
        return payload

    def void(
        self, entry_id: str, *, reason: str, resolver: str, ts: str | None = None
    ) -> dict[str, Any]:
        self.require()
        if not reason.strip():
            raise IntegrityError("void: reason is required")
        with self._exclusive():
            current = self.state()
            if entry_id not in current:
                raise IntegrityError(f"void: unknown entry {entry_id!r}")
            record = current[entry_id]
            if record["status"] not in ("draft", "open"):
                raise IntegrityError(
                    f"void: {entry_id} is {record['status']}, only a draft or open entry can be voided"
                )
            payload = {"reason": reason, "resolver": resolver, "voided_at": ts or utc_now()}
            self._append_event(
                action="void", entry_id=entry_id, payload=payload, actor=resolver, ts=ts
            )
        return payload

    # -- verification ------------------------------------------------------
    def verify(self) -> list[str]:
        """Check the hash chain and the agreement between the two files."""
        errors: list[str] = []
        try:
            events = self._read_events()
        except IntegrityError as exc:
            return [str(exc)]
        previous = GENESIS
        for index, event in enumerate(events, start=1):
            if event.get("seq") != index:
                errors.append(f"{EVENTS_FILE} seq {event.get('seq')}: expected seq {index}")
            if event.get("prev_hash") != previous:
                errors.append(
                    f"{EVENTS_FILE} seq {index}: prev_hash does not match the previous event"
                )
            expected = event_digest(event)
            if event.get("hash") != expected:
                errors.append(
                    f"{EVENTS_FILE} seq {index}: hash mismatch "
                    f"(stored {str(event.get('hash'))[:14]}…, computed {expected[:14]}…)"
                )
            previous = str(event.get("hash"))

        try:
            entries = self.entries_by_id()
        except IntegrityError as exc:
            errors.append(str(exc))
            return errors

        created: set[str] = set()
        for event in events:
            if event.get("action") != "create":
                continue
            entry_id = str(event.get("entry", ""))
            payload = event.get("payload") or {}
            snapshot = payload.get("entry")
            recorded_hash = payload.get("entry_hash")
            if entry_id in created:
                errors.append(f"{EVENTS_FILE}: duplicate create for {entry_id}")
            created.add(entry_id)
            if entry_id not in entries:
                errors.append(f"{EVENTS_FILE}: create for {entry_id} has no line in {LEDGER_FILE}")
                continue
            if snapshot != entries[entry_id].to_dict():
                errors.append(
                    f"{LEDGER_FILE}: entry {entry_id} was altered after creation "
                    "(snapshot in the event log differs)"
                )
            computed = sha256_hex(canonical(entries[entry_id].to_dict()))
            if recorded_hash != computed:
                errors.append(f"{LEDGER_FILE}: entry {entry_id} hash mismatch")

        for entry_id in sorted(set(entries) - created):
            errors.append(f"{LEDGER_FILE}: entry {entry_id} has no create event")
        return errors

    def validate(self) -> tuple[list[str], list[str]]:
        """Return (errors, warnings). Errors map to exit code 2, warnings are printed."""
        errors = self.verify()
        warnings: list[str] = []

        try:
            entries = self.entries()
        except IntegrityError as exc:
            return errors + [str(exc)], warnings

        for entry in entries:
            errors.extend(entry.errors())

        state: dict[str, dict[str, Any]] = {}
        try:
            state = self.state()
        except IntegrityError as exc:
            errors.append(str(exc))
            return errors, warnings

        for entry_id, record in sorted(state.items()):
            resolution = record["resolution"]
            if record["status"] == "resolved" and isinstance(resolution, dict):
                evidence = Evidence.from_dict(resolution.get("evidence"))
                problems = resolution_errors(
                    resolution.get("outcome"), evidence, str(resolution.get("resolved_at", ""))
                )
                errors.extend(f"entry {entry_id}: {problem}" for problem in problems)
            if record["status"] == "void" and not str(
                (record["void"] or {}).get("reason", "")
            ).strip():
                errors.append(f"entry {entry_id}: voided without a reason")

        from .model import utc_now

        today = parse_iso_date(utc_now()[:10], "today")
        overdue = [
            entry_id
            for entry_id, record in state.items()
            if record["status"] == "open"
            and parse_iso_date(record["entry"].due, "due") < today
        ]
        if overdue:
            warnings.append(
                f"{len(overdue)} open entr{'y' if len(overdue) == 1 else 'ies'} past the due date: "
                + ", ".join(sorted(overdue))
            )
        without_origin = [
            entry_id for entry_id, record in state.items() if not record["entry"].origin
        ]
        if without_origin:
            warnings.append(
                f"{len(without_origin)} entr{'y' if len(without_origin) == 1 else 'ies'} "
                "without an origin tag"
            )
        return errors, warnings
