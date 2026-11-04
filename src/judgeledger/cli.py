"""Command line interface. Exit codes are part of the contract: 0 ok, 2 integrity, 3 insufficient."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from . import __version__
from .demo import build as build_demo
from .model import Evidence, IntegrityError, utc_now
from .report import build as build_report
from .report import digest
from .scoring import summarize
from .store import Ledger

EXIT_OK = 0
EXIT_INTEGRITY = 2
EXIT_INSUFFICIENT = 3


def _actor(args: argparse.Namespace) -> str:
    return args.actor or os.environ.get("JL_ACTOR") or getpass.getuser()


def _ledger(args: argparse.Namespace) -> Ledger:
    ledger = Ledger(args.dir)
    ledger.require()
    return ledger


def _number(value: float | None) -> str:
    return "—" if value is None else f"{value:.4f}"


def _percent(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


# -- commands --------------------------------------------------------------
def cmd_init(args: argparse.Namespace) -> int:
    Ledger.init(args.dir, _actor(args))
    print(f"initialised {Path(args.dir)}")
    return EXIT_OK


def cmd_add(args: argparse.Namespace) -> int:
    ledger = _ledger(args)
    kind = "interval" if args.interval else "point"
    entry = ledger.add(
        question=args.question,
        criteria=args.criteria,
        due=args.due,
        kind=kind,
        actor=_actor(args),
        point=args.point,
        interval=tuple(args.interval) if args.interval else None,
        tags=[tag.strip() for tag in (args.tags or "").split(",") if tag.strip()],
        origin=args.origin,
    )
    print(f"{entry.id} created as draft — {entry.as_forecast()}, due {entry.due}")
    print(f"open it with: jl open {entry.id}")
    return EXIT_OK


def cmd_open(args: argparse.Namespace) -> int:
    ledger = _ledger(args)
    state = ledger.state()
    targets = args.ids or [
        entry_id for entry_id, record in state.items() if record["status"] == "draft"
    ]
    if not targets:
        raise IntegrityError("open: no draft entries to open")
    for entry_id in targets:
        ledger.open_entry(entry_id, _actor(args))
        print(f"{entry_id} open — question and criteria are now locked")
    return EXIT_OK


def cmd_resolve(args: argparse.Namespace) -> int:
    ledger = _ledger(args)
    evidence = Evidence(
        citation=args.citation,
        url=args.url or "",
        archive_url=args.archive_url or "",
        excerpt=args.excerpt or "",
    )
    payload = ledger.resolve(
        args.id,
        outcome=args.outcome,
        evidence=evidence,
        resolver=args.resolver or _actor(args),
        resolved_at=args.at,
    )
    late = " (late)" if payload.get("late") else ""
    print(f"{args.id} resolved with outcome {payload['outcome']}{late}")
    return EXIT_OK


def cmd_void(args: argparse.Namespace) -> int:
    ledger = _ledger(args)
    ledger.void(args.id, reason=args.reason, resolver=args.resolver or _actor(args))
    print(f"{args.id} voided — reason recorded")
    return EXIT_OK


def _print_summary(summary: dict[str, Any]) -> None:
    counts = summary["counts"]
    print(
        f"{counts['entries']} entries · {counts['resolved']} resolved · {counts['open']} open · "
        f"{counts['draft']} draft · {counts['void']} void"
    )
    if not counts["resolved"]:
        print("no resolved judgments — nothing to score")
        return
    print(f"CRPS (mean)      {_number(summary['crps_mean'])}")
    print(f"Brier (midpoint) {_number(summary['brier_mean'])}")
    print(f"Base rate        {_percent(summary['base_rate'])}")
    print(f"Sharpness        {_number(summary['sharpness'])}")
    if not summary["sufficient"]:
        print(
            f"insufficient sample: {counts['resolved']} < {summary['minimum_sample']}; "
            "calibration curve not reported"
        )
        return
    murphy = summary["murphy"] or {}
    print(
        f"Murphy           REL {_number(murphy.get('reliability'))} · "
        f"RES {_number(murphy.get('resolution'))} · UNC {_number(murphy.get('uncertainty'))}"
    )
    print("calibration (bin · n · forecast · observed)")
    for row in murphy.get("bins", []):
        flag = " (n<5)" if row["n"] < 5 else ""
        print(f"  {row['bin']} · {row['n']} · {row['forecast']:.3f} · {row['observed']:.3f}{flag}")
    hygiene = summary["hygiene"]
    print(
        f"hygiene          void {_percent(hygiene['void_rate'])} · "
        f"overdue open {hygiene['overdue_open']} · without origin {hygiene['without_origin']}"
    )


def cmd_score(args: argparse.Namespace) -> int:
    ledger = _ledger(args)
    summary = summarize(ledger.state(), minimum_sample=args.minimum_sample, as_of=args.as_of)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_summary(summary)
    return EXIT_OK if summary["sufficient"] else EXIT_INSUFFICIENT


def cmd_report(args: argparse.Namespace) -> int:
    ledger = _ledger(args)
    markdown = build_report(
        ledger.state(), minimum_sample=args.minimum_sample, as_of=args.as_of
    )
    checksum = digest(markdown)
    if args.md:
        Path(args.md).write_text(markdown, encoding="utf-8")
        print(f"wrote {args.md} sha256={checksum}")
    else:
        print(markdown, end="")
        print(f"sha256={checksum}", file=sys.stderr)
    return EXIT_OK


def cmd_validate(args: argparse.Namespace) -> int:
    ledger = _ledger(args)
    errors, warnings = ledger.validate()
    for warning in warnings:
        print(f"warning: {warning}")
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    print(f"{len(errors)} error(s), {len(warnings)} warning(s)")
    return EXIT_INTEGRITY if errors else EXIT_OK


def cmd_verify(args: argparse.Namespace) -> int:
    ledger = _ledger(args)
    errors = ledger.verify()
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return EXIT_INTEGRITY
    print(f"chain ok: {len(ledger.events())} events")
    return EXIT_OK


def cmd_list(args: argparse.Namespace) -> int:
    ledger = _ledger(args)
    rows = []
    for entry_id, record in sorted(ledger.state().items()):
        if args.status and record["status"] != args.status:
            continue
        entry = record["entry"]
        rows.append(
            f"{entry.id}  {record['status']:<8}  {entry.due}  {entry.as_forecast():<12}  "
            f"{' '.join(entry.question.split())[:70]}"
        )
    print("\n".join(rows) if rows else "no entries")
    return EXIT_OK


def cmd_import_achlab(args: argparse.Namespace) -> int:
    path = Path(args.project)
    try:
        project = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IntegrityError(f"import: cannot read {path}: {exc}") from exc
    if not isinstance(project, dict):
        raise IntegrityError(f"import: {path} is not a JSON object")

    hypothesis = None
    for item in project.get("hypotheses") or []:
        if isinstance(item, dict) and str(item.get("id")) == args.hypothesis:
            hypothesis = item
            break
    if hypothesis is None:
        raise IntegrityError(f"import: hypothesis {args.hypothesis!r} not found in {path.name}")
    if not args.interval:
        raise IntegrityError(
            "import: an achlab confidence band is not a probability. Pass --interval L U to "
            "declare the probability interval you are committing to; the band describes the "
            "analysis, not the hypothesis."
        )

    statement = str(hypothesis.get("statement", "")).strip()
    question = f"{args.hypothesis}: {statement}" if statement else str(project.get("question", ""))
    origin = f"achlab:{path.stem}#{args.hypothesis}"
    if args.band:
        origin += f" [{args.band}]"

    ledger = _ledger(args)
    entry = ledger.add(
        question=question or f"{args.hypothesis} from {path.stem}",
        criteria=args.criteria,
        due=args.due,
        kind="interval",
        actor=_actor(args),
        interval=tuple(args.interval),
        tags=[tag.strip() for tag in (args.tags or "").split(",") if tag.strip()],
        origin=origin,
    )
    print(f"{entry.id} imported from {path.name} — {entry.as_forecast()}, due {entry.due}")
    return EXIT_OK


def cmd_demo(args: argparse.Namespace) -> int:
    if args.write:
        target = Path(args.write)
        if target.exists() and any(target.iterdir()):
            raise IntegrityError(f"demo: {target} exists and is not empty")
        ledger = build_demo(str(target))
        markdown = build_report(ledger.state(), as_of=args.as_of)
        print(f"wrote demo ledger to {target} sha256={digest(markdown)}")
        return EXIT_OK
    temp = tempfile.mkdtemp(prefix="judgeledger-demo-")
    try:
        ledger = build_demo(temp)
        markdown = build_report(ledger.state(), as_of=args.as_of)
        print(markdown, end="")
        print(f"sha256={digest(markdown)}", file=sys.stderr)
    finally:
        shutil.rmtree(temp, ignore_errors=True)
    return EXIT_OK


# -- parser ----------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jl",
        description=(
            "Local, hash-chained ledger of analytic judgments: question and resolution criteria "
            "locked before the fact, resolutions carry a source."
        ),
    )
    parser.add_argument("--version", action="version", version=f"judgeledger {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(target: argparse.ArgumentParser, with_dir: bool = True) -> None:
        if with_dir:
            target.add_argument("--dir", default=".", help="ledger directory (default: .)")
        target.add_argument("--actor", default="", help="who is acting (default: $JL_ACTOR or user)")

    p_init = sub.add_parser("init", help="create a ledger directory")
    p_init.add_argument("dir")
    p_init.add_argument("--actor", default="", help="who owns the ledger")
    p_init.set_defaults(func=cmd_init)

    p_add = sub.add_parser("add", help="add a judgment as draft")
    p_add.add_argument("question")
    p_add.add_argument("--criteria", required=True, help="what settles the question")
    p_add.add_argument("--due", required=True, help="resolution deadline (YYYY-MM-DD)")
    forecast = p_add.add_mutually_exclusive_group(required=True)
    forecast.add_argument("--point", type=float, help="point probability in [0,1]")
    forecast.add_argument(
        "--interval", type=float, nargs=2, metavar=("LOW", "HIGH"), help="probability interval"
    )
    p_add.add_argument("--tags", default="", help="comma-separated tags")
    p_add.add_argument("--origin", default=None, help="where the judgment comes from")
    common(p_add)
    p_add.set_defaults(func=cmd_add)

    p_open = sub.add_parser("open", help="lock drafts (all of them when no id is given)")
    p_open.add_argument("ids", nargs="*")
    common(p_open)
    p_open.set_defaults(func=cmd_open)

    p_resolve = sub.add_parser("resolve", help="record the outcome, with a source")
    p_resolve.add_argument("id")
    p_resolve.add_argument("--outcome", type=int, choices=(0, 1), required=True)
    p_resolve.add_argument("--citation", required=True, help="citation text of the source")
    p_resolve.add_argument("--url", default="", help="where the source lives")
    p_resolve.add_argument("--archive-url", default="", help="archived copy of the source")
    p_resolve.add_argument("--excerpt", default="", help="quoted passage, <=500 chars")
    p_resolve.add_argument("--resolver", default="", help="who resolved it")
    p_resolve.add_argument("--at", default=None, help="resolution timestamp (ISO-8601)")
    common(p_resolve)
    p_resolve.set_defaults(func=cmd_resolve)

    p_void = sub.add_parser("void", help="annul a question whose criteria failed")
    p_void.add_argument("id")
    p_void.add_argument("--reason", required=True)
    p_void.add_argument("--resolver", default="")
    common(p_void)
    p_void.set_defaults(func=cmd_void)

    p_score = sub.add_parser("score", help="score the ledger")
    p_score.add_argument("--json", action="store_true")
    p_score.add_argument("--minimum-sample", type=int, default=20)
    p_score.add_argument("--as-of", default=None, help="date the overdue count is measured on")
    common(p_score)
    p_score.set_defaults(func=cmd_score)

    p_report = sub.add_parser("report", help="render a Markdown report")
    p_report.add_argument("--md", default="", help="write to this path instead of stdout")
    p_report.add_argument("--minimum-sample", type=int, default=20)
    p_report.add_argument("--as-of", default=None)
    common(p_report)
    p_report.set_defaults(func=cmd_report)

    p_validate = sub.add_parser("validate", help="check the integrity rules")
    common(p_validate)
    p_validate.set_defaults(func=cmd_validate)

    p_verify = sub.add_parser("verify", help="check the hash chain")
    common(p_verify)
    p_verify.set_defaults(func=cmd_verify)

    p_list = sub.add_parser("list", help="list entries")
    p_list.add_argument("--status", choices=("draft", "open", "resolved", "void"), default=None)
    common(p_list)
    p_list.set_defaults(func=cmd_list)

    p_import = sub.add_parser("import", help="import a judgment from an achlab project")
    p_import.add_argument("project", help="path to the achlab project JSON")
    p_import.add_argument("--hypothesis", required=True)
    p_import.add_argument(
        "--interval",
        type=float,
        nargs=2,
        metavar=("LOW", "HIGH"),
        help="probability interval you commit to (required: a band is not a probability)",
    )
    p_import.add_argument("--criteria", required=True)
    p_import.add_argument("--due", required=True)
    p_import.add_argument("--band", default="", help="the achlab band, kept as metadata only")
    p_import.add_argument("--tags", default="")
    common(p_import)
    p_import.set_defaults(func=cmd_import_achlab)

    p_demo = sub.add_parser("demo", help="run the synthetic demo ledger")
    p_demo.add_argument("--write", default="", help="materialise the demo ledger at this path")
    p_demo.add_argument("--as-of", default=None)
    p_demo.set_defaults(func=cmd_demo)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except IntegrityError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INTEGRITY
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
