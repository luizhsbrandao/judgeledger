#!/usr/bin/env bash
# Smoke test of the CLI contract: exit codes, not just "it ran".
set -euo pipefail

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

jl demo > /dev/null
jl demo --write "$work/ledger" > /dev/null
jl validate --dir "$work/ledger" > /dev/null
jl verify --dir "$work/ledger" > /dev/null
jl report --dir "$work/ledger" --as-of 2026-11-04 --md "$work/report.md" > /dev/null

# Tamper with one locked criterion and require exit 2.
python - "$work/ledger/ledger.jsonl" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
lines = path.read_text(encoding="utf-8").splitlines()
record = json.loads(lines[0])
record["criteria"] = "rewritten after the fact, comfortably long enough"
lines[0] = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

set +e
jl validate --dir "$work/ledger" > /dev/null 2>&1
tampered=$?
set -e
if [ "$tampered" -ne 2 ]; then
  echo "expected exit 2 after a tampered criterion, got $tampered" >&2
  exit 1
fi

# A single resolved judgment is below the minimum sample: exit 3.
jl init "$work/small" --actor ci > /dev/null
jl add "Only one judgment" --criteria "Stated in the official published record" \
  --due 2026-12-31 --point 0.5 --dir "$work/small" > /dev/null
jl open --dir "$work/small" > /dev/null
jl resolve E001 --outcome 1 --citation "Synthetic record" \
  --url https://example.org/record --dir "$work/small" > /dev/null

set +e
jl score --dir "$work/small" > /dev/null
small=$?
set -e
if [ "$small" -ne 3 ]; then
  echo "expected exit 3 below the minimum sample, got $small" >&2
  exit 1
fi

echo "smoke ok: exit codes 0/2/3 as documented"
