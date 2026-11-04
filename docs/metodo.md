# Method: what an entry is, and what the report is allowed to say

## 1. The judgment, not the opinion

An entry is a claim that can be settled. It needs three things before it counts:

1. **a question** with a truth value at a date — "the pilot ships module 2 by 31/03", not "the pilot
   is going well";
2. **a resolution criterion** — the observable fact that will settle it, including the window;
3. **a deadline** — after which the entry is either resolved or overdue, never quietly forgotten.

The criterion is locked when the entry is created. This is the whole method: an analyst who can
reword the criterion after seeing the outcome has no track record, only a memory.

### Criteria that are actually bad

`jl` cannot judge whether a criterion is *good*, only whether it is *present*. In practice the
failures look like this:

| Bad criterion | Why it fails | What to write instead |
|---|---|---|
| "the project will be delayed" | no threshold, no date | "the delivery date published in the project portal moves past 30/06" |
| "support drops" | no metric, no window | "the monthly poll average falls below 40% for two consecutive months" |
| "the report is criticised" | no source, no threshold | "at least two of the four named outlets publish a critical editorial within 7 days" |

When the criterion turns out to be unsettleable, the entry is `void` with a reason — counted apart
from hits and misses, and visible in the hygiene block (`void rate`). A high void rate is a reading
about the analyst's criteria, not about the world.

## 2. What the report may claim

The report is a description of the ledger, not an inference about the future or about competence:

- **CRPS mean** — how expensive the stated uncertainty was, on average, against the outcomes;
- **Brier at the midpoint** — the familiar number, for readers who want it;
- **sharpness** — the average width of what was declared. A high sharpness with a bad CRPS is
  overconfidence; a low sharpness with a good CRPS may be hedging;
- **base rate** — the fraction of resolved judgments that came true. Without it the other numbers
  are unreadable: a sample where 90% of events happen makes a 90% band look clever;
- **calibration per bin** — mean forecast versus observed frequency; the diagonal is honesty;
- **bands by declared width** — see `docs/pontuacao.md` §4: a binary outcome cannot fall inside a
  probability band, so the comparison is at group level;
- **windows** by horizon and by quarter — a single lucky quarter shows up as a spike instead of
  becoming a thesis;
- **hygiene** — void rate, overdue entries, entries without an origin.

Everything is printed with its `n`. A number without a sample size is a decoration.

## 3. What it cannot claim

- **Not causal.** A good CRPS does not mean the method was good; it means the stated intervals were
  close to the outcomes.
- **Not comparable across ledgers.** CRPS depends on the base rate of what you choose to log. Two
  ledgers with different event mixes cannot be ranked, which is why there is no leaderboard.
- **Not immune to selection.** You choose what to record. The only defence is the discipline of
  logging every judgment that matters, including the ones you would rather forget — and the
  `without origin` count exists to make the ones you did not log visible.
- **Not a forecast of anything.** The ledger scores judgments already made.

## 4. Reading a report in one pass

1. `entries` vs `resolved`: is the ledger actually being used, or accumulating?
2. `void rate`: are the criteria settleable?
3. `CRPS` against `base rate`: better or worse than "always say the base rate"?
4. calibration table: is the error in the middle (noise) or at the extremes (overconfidence)?
5. bands: does the width you declare match the frequency you get?
6. windows: is one quarter carrying the result?

If step 1 fails, nothing after it matters.
