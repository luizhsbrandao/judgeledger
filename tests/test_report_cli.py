"""Report and CLI: determinism, exit codes, the end-to-end flow."""

from __future__ import annotations

import json

import pytest

from judgeledger import cli
from judgeledger.demo import build as build_demo
from judgeledger.report import build as build_report
from judgeledger.report import digest
from judgeledger.scoring import summarize
from judgeledger.store import Ledger
from helpers import add, seed


def test_report_is_deterministic(ledger) -> None:
    seed(ledger, 22)
    state = ledger.state()
    first = build_report(state, as_of="2026-12-31")
    second = build_report(state, as_of="2026-12-31")
    assert first == second
    assert digest(first) == digest(second)


def test_report_flags_an_insufficient_sample(ledger) -> None:
    seed(ledger, 7)
    markdown = build_report(ledger.state(), as_of="2026-12-31")
    assert "INSUFFICIENT SAMPLE" in markdown
    assert "Calibration" not in markdown


def test_report_lists_sources(ledger) -> None:
    add(ledger, outcome=1)
    markdown = build_report(ledger.state(), as_of="2026-12-31")
    assert "https://example.org/record" in markdown
    assert "## Sources" in markdown


def test_report_without_resolved_entries(ledger) -> None:
    add(ledger, outcome=None)
    markdown = build_report(ledger.state(), as_of="2026-12-31")
    assert "NO RESOLVED JUDGMENTS" in markdown


def test_demo_exits_zero_and_prints_the_report(capsys) -> None:
    assert cli.main(["demo"]) == 0
    out = capsys.readouterr().out
    assert "# judgeledger report" in out
    assert "## Scores" in out
    assert "44 entries" in out


def test_demo_files_are_byte_identical_across_runs(tmp_path) -> None:
    first = build_demo(str(tmp_path / "first"))
    second = build_demo(str(tmp_path / "second"))
    assert first.ledger_path.read_bytes() == second.ledger_path.read_bytes()
    assert first.events_path.read_bytes() == second.events_path.read_bytes()


def test_demo_validates_and_verifies(tmp_path) -> None:
    ledger = build_demo(str(tmp_path / "demo"))
    errors, _warnings = ledger.validate()
    assert errors == []
    assert ledger.verify() == []
    summary = summarize(ledger.state())
    assert summary["counts"]["resolved"] == 40
    assert summary["sufficient"] is True


def test_score_exits_three_below_the_minimum(ledger) -> None:
    seed(ledger, 7)
    assert cli.main(["score", "--dir", str(ledger.root)]) == 3


def test_score_json_is_machine_readable(ledger, capsys) -> None:
    seed(ledger, 21)
    assert cli.main(["score", "--dir", str(ledger.root), "--json", "--as-of", "2026-12-31"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["counts"]["resolved"] == 21
    assert 0.0 <= payload["base_rate"] <= 1.0


def test_report_md_writes_the_file_and_prints_the_digest(ledger, tmp_path, capsys) -> None:
    seed(ledger, 21)
    target = tmp_path / "report.md"
    assert cli.main(
        ["report", "--dir", str(ledger.root), "--md", str(target), "--as-of", "2026-12-31"]
    ) == 0
    out = capsys.readouterr().out
    assert target.read_text(encoding="utf-8").startswith("# judgeledger report")
    assert "sha256=" in out


def test_validate_exits_two_after_a_tamper(ledger, capsys) -> None:
    add(ledger, outcome=1)
    lines = ledger.ledger_path.read_text().splitlines()
    record = json.loads(lines[0])
    record["question"] = "A different question"
    lines[0] = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    ledger.ledger_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert cli.main(["validate", "--dir", str(ledger.root)]) == 2
    assert "error:" in capsys.readouterr().err


def test_verify_is_clean_on_a_fresh_ledger(ledger, capsys) -> None:
    add(ledger, outcome=1)
    assert cli.main(["verify", "--dir", str(ledger.root)]) == 0
    assert "chain ok" in capsys.readouterr().out


def test_add_open_resolve_flow(tmp_path, capsys) -> None:
    root = tmp_path / "flow"
    assert cli.main(["init", str(root), "--actor", "tester"]) == 0
    assert cli.main(
        [
            "add",
            "Will the pilot finish on time?",
            "--criteria",
            "Acceptance note signed by the sponsor",
            "--due",
            "2026-12-31",
            "--interval",
            "0.55",
            "0.8",
            "--dir",
            str(root),
        ]
    ) == 0
    assert cli.main(["open", "--dir", str(root), "--actor", "tester"]) == 0
    assert cli.main(
        [
            "resolve",
            "E001",
            "--outcome",
            "1",
            "--citation",
            "Acceptance note 44/2026",
            "--url",
            "https://example.org/note-44",
            "--dir",
            str(root),
            "--actor",
            "tester",
        ]
    ) == 0
    assert cli.main(["list", "--dir", str(root)]) == 0
    out = capsys.readouterr().out
    assert "resolved" in out
    ledger = Ledger(root)
    assert ledger.validate()[0] == []


def test_resolve_without_source_exits_two(ledger, capsys) -> None:
    entry = add(ledger, outcome=None)
    assert cli.main(
        ["resolve", entry.id, "--outcome", "1", "--citation", "", "--dir", str(ledger.root)]
    ) == 2
    assert "citation" in capsys.readouterr().err


def test_import_refuses_a_band_without_an_interval(ledger, tmp_path, capsys) -> None:
    project = tmp_path / "caso.json"
    project.write_text(
        json.dumps({"question": "Q?", "hypotheses": [{"id": "H1", "statement": "S"}]}),
        encoding="utf-8",
    )
    code = cli.main(
        [
            "import",
            str(project),
            "--hypothesis",
            "H1",
            "--criteria",
            "Stated in the official record",
            "--due",
            "2026-12-31",
            "--dir",
            str(ledger.root),
        ]
    )
    assert code == 2
    assert "not a probability" in capsys.readouterr().err


def test_import_with_interval_creates_the_entry(ledger, tmp_path) -> None:
    project = tmp_path / "caso.json"
    project.write_text(
        json.dumps(
            {"question": "Who leaked?", "hypotheses": [{"id": "H2", "statement": "An outsider."}]}
        ),
        encoding="utf-8",
    )
    code = cli.main(
        [
            "import",
            str(project),
            "--hypothesis",
            "H2",
            "--interval",
            "0.6",
            "0.85",
            "--band",
            "MODERADA",
            "--criteria",
            "Stated in the official record",
            "--due",
            "2026-12-31",
            "--dir",
            str(ledger.root),
        ]
    )
    assert code == 0
    entry = ledger.entries()[0]
    assert entry.origin == "achlab:caso#H2 [MODERADA]"
    assert entry.question.startswith("H2: An outsider.")
    assert entry.kind == "interval"


def test_import_with_unknown_hypothesis_exits_two(ledger, tmp_path, capsys) -> None:
    project = tmp_path / "caso.json"
    project.write_text(json.dumps({"question": "Q?", "hypotheses": []}), encoding="utf-8")
    assert cli.main(
        [
            "import",
            str(project),
            "--hypothesis",
            "H9",
            "--interval",
            "0.5",
            "0.7",
            "--criteria",
            "Stated in the official record",
            "--due",
            "2026-12-31",
            "--dir",
            str(ledger.root),
        ]
    ) == 2
    assert "not found" in capsys.readouterr().err


def test_open_with_no_drafts_exits_two(ledger, capsys) -> None:
    assert cli.main(["open", "--dir", str(ledger.root)]) == 2
    assert "no draft entries" in capsys.readouterr().err


@pytest.mark.parametrize("command", ["validate", "verify", "score", "list"])
def test_commands_refuse_a_missing_ledger(tmp_path, capsys, command) -> None:
    assert cli.main([command, "--dir", str(tmp_path / "nope")]) == 2
    assert "no ledger here" in capsys.readouterr().err
