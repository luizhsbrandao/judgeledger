# Contributing

Thanks for looking. This project is small on purpose, and the constraints below are what keep it
useful.

## Setup

```console
$ python -m venv .venv && . .venv/bin/activate
$ pip install -e ".[dev]"
$ python -m pytest
```

Python 3.11 or newer. The runtime has no dependencies; `pytest` is the only development one.

## Rules that are not negotiable

1. **Determinism.** The same ledger and the same `--as-of` date must produce byte-identical output.
   Nothing in the report may read the clock, the locale or the environment.
2. **Exit codes are the contract.** `0` ok, `2` integrity violation, `3` insufficient sample. A new
   failure mode has to fit one of them; a fourth code breaks scripts.
3. **`ledger.jsonl` is never rewritten.** Corrections are `void` + a new entry. Do not add an edit
   path, even for typos: an editable entry is the property this tool exists to remove.
4. **No runtime dependencies.** Standard library only. If a feature needs a library, it is probably
   out of scope for the core.
5. **No LLM, no network, no automatic resolution.** The judgment and its source are human.
6. **Test the property, not the number.** A change to `scoring.py` needs a property test (symmetry,
   monotonicity, an independent identity), not just an updated expected value.

## Pull requests

- One change per PR, with the reasoning in the description.
- `python -m pytest` green on 3.11 and 3.13 (CI runs both; run locally what you can).
- If the change touches the data model, update `schema/entry.schema.json` in the same PR — a test
  asserts the schema's required fields match `Entry.to_dict()`.
- If it changes behaviour, update the README section and the matching `docs/` page in the same PR.

## Data

Never commit a real ledger, a real citation you do not have the right to redistribute, or any
personal data. New examples must be synthetic and must use reserved domains (`example.org`).
