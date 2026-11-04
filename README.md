# judgeledger

*Português: [README.pt-BR.md](README.pt-BR.md).*

A local ledger of analytic judgments. You write down the question **and the criterion that will
settle it** before the fact; the entry is hashed into an append-only log; when the outcome lands you
resolve it with a citation. The report then tells you whether your stated uncertainty was real.

```console
$ jl add "Programa Alfa ships module 2 by 31/03" \
    --criteria "Signed release notes and a production deploy in the changelog" \
    --due 2025-03-31 --interval 0.60 0.80
E001 created as draft — [0.60, 0.80], due 2025-03-31
```

## Why not an existing calibration tracker?

The arithmetic is not the gap. `scikit-learn` ships `brier_score_loss` and `calibration_curve`;
`forecast-calibration-kit` implements Brier, log loss, ECE and the Murphy decomposition;
`brierly` already runs the log → resolve → score loop as a local PWA. Recomputing those numbers
would add nothing.

The gap is **integrity**. None of them stops you from rewriting the question, or the resolution
criterion, after you already know the answer — which makes the track record they produce
contestable, and a contestable track record cannot defend a judgment. judgeledger enforces the
properties instead:

- **locked at creation** — question, criteria and deadline are hashed into the event log; editing
  them afterwards is an integrity error, not an edit;
- **no backdating** — the deadline must be after the creation date;
- **source or it did not happen** — a resolution needs a citation plus a URL (or archive URL);
- **annulled is not wrong** — a question whose criteria failed is `void`, with a reason, counted
  apart from hits and misses;
- **the chain is checkable** — every action carries the digest of the previous event.

## Install

PyPI publication is pending (the trusted publisher is configured on the account side, not yet on
the project). Until it lands, install straight from the repository:

```console
$ pipx install git+https://github.com/luizhsbrandao/judgeledger
# or: uv tool install git+https://github.com/luizhsbrandao/judgeledger
```

When 0.1.0 is on the index this becomes `pipx install judgeledger`. Python ≥ 3.11, no runtime
dependencies.

## Usage

```console
$ jl init ledger-2027 --actor LH
$ jl add "H2 collapses before 2027-06" \
    --criteria "Two consecutive monthly readings below the stated threshold" \
    --due 2027-06-30 --interval 0.55 0.80 --tags ira --origin achlab:caso-11#H2
$ jl open                     # locks every draft; nothing can be reworded from here
$ jl resolve E001 --outcome 1 \
    --citation "Relatório Z, p. 12" --url https://example.org/z-12 --excerpt "…"
$ jl score                    # CRPS, Brier, coverage, sharpness, Murphy
$ jl report --md report.md    # deterministic Markdown, with the sources
$ jl validate                 # exit 2 on any integrity violation
$ jl verify                   # exit 2 when the hash chain is broken
$ jl demo                     # 44 synthetic judgments, 40 resolved
```

Exit codes are the contract: `0` ok, `2` integrity violation, `3` not enough data to report a
calibration curve (fewer than 20 resolved judgments).

## Scoring

The unit of forecast is an interval `[l, u]`; a point forecast is the degenerate interval `[p, p]`.
The primary score is the CRPS of the uniform distribution on that interval against the binary
outcome, in closed form:

```
CRPS([l,u], y) = (u−l)/3 + (l−y)      if y ≤ l
                 (u−l)/3 + (y−u)      if y ≥ u
                 [(y−l)³ + (u−y)³] / (3(u−l)²)   if l < y < u
```

CRPS is strictly proper, so stating your real uncertainty is the optimal strategy: widening the
band to hedge costs you, and so does narrowing it without basis. The Brier score at the midpoint is
reported next to it for familiarity, but never ranks the judgments — it rewards a narrow band on its
own. Calibration is shown per bin; the declared bands are compared with the observed frequency per
width bucket (a binary outcome cannot fall inside a probability band, so that check is at group
level); and the decomposition `BS = REL − RES + UNC` is printed so anyone can recompute it. See
[`docs/pontuacao.md`](docs/pontuacao.md) for a worked example.

## Importing from an ACH analysis

`jl import achlab case.json --hypothesis H2 --interval 0.6 0.85` turns a hypothesis from an
[`achlab`](https://github.com/luizhsbrandao/achlab) case into a scorable judgment. The `--interval`
is **required**: the confidence band describes the analysis, not the probability of the hypothesis,
so it is carried as metadata and never converted into a number by the tool.

## What it does not do

- no server, no accounts, no web UI — the ledger is a directory you can put in git;
- no LLM, and no automatic resolution (no scraping, no market prices): a human resolves it, with a
  source;
- no leaderboard and no comparison between ledgers;
- no cryptographic signature — the hash chain detects accidental or opportunistic edits, not an
  adversary who holds the whole file. `SECURITY.md` says the same.

## Data

Everything under `examples/` is synthetic. A real ledger is personal: keep it out of the public
repository (`.gitignore` covers `ledger/`). No classified information, no personal data.

## Development

```console
$ python -m venv .venv && . .venv/bin/activate
$ pip install -e ".[dev]"
$ python -m pytest
```

The suite covers the closed form of the CRPS against numerical integration, every integrity rule,
tampering with either file, determinism of the report, and the CLI exit codes.

## License

MIT.

## Gate de segredo (pre-commit)

Todo clone precisa ativar o hook **uma vez** — `core.hooksPath` é config local e não
viaja com o checkout (worktrees compartilham, porque leem o mesmo config do repo):

```bash
git config core.hooksPath .githooks
```

`.githooks/pre-commit` roda `gitleaks` com as regras de `.gitleaks.toml` sobre o
conteúdo staged e **falha fechado**: sem o binário no `PATH` ou sem o `.toml`, o commit
para. Bypass consciente é `git commit --no-verify`, com o motivo registrado no commit.

