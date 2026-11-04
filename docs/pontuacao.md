# Scoring

The unit of forecast is a probability interval `[l, u]` over the event happening (`1`) or not (`0`).
A point forecast is the degenerate interval `[p, p]`. Because both kinds live on the same scale, the
ledger can rank them together without a special case.

## 1. Primary score: CRPS of the uniform on `[l, u]`

The Continuous Ranked Probability Score for a forecast distribution `F` and outcome `y` is

```
CRPS(F, y) = ∫ (F(x) − 1{y ≤ x})² dx
```

For `F = Uniform[l, u]` the integral has a closed form:

```
CRPS([l,u], y) = (u−l)/3 + (l−y)                   if y ≤ l
                 (u−l)/3 + (y−u)                   if y ≥ u
                 [(y−l)³ + (u−y)³] / (3(u−l)²)      if l < y < u
```

The tail terms are the part a quick derivation drops: when `y` lies outside the interval the CDF is
already saturated, and the indicator only flips at `y`, leaving a slab where the integrand equals 1
and whose length is `|y − u|` (or `|l − y|`). Omitting them understates the cost of a confident miss
by exactly that slab. The test suite checks the formula against numerical integration with the
kinks at `l`, `u` and `y`, and against the independent identity
`CRPS = E|X − y| − ½E|X − X′|`.

### Binary outcomes collapse it to a linear form

Since `y ∈ {0, 1}` and `0 ≤ l ≤ u ≤ 1`, the middle branch is unreachable in practice (it exists for
a future continuous-outcome mode). The two live branches simplify to

```
CRPS([l,u], 0) = (u + 2l) / 3
CRPS([l,u], 1) = (3 − 2u − l) / 3
```

Worked examples, all checked against the implementation:

| Interval | Outcome | CRPS | Reading |
|---|---|---|---|
| `[0.20, 0.80]` | 1 | 0.4000 | the band covered the outcome |
| `[0.60, 0.80]` | 1 | 0.2667 | narrower and right: cheaper |
| `[0.60, 0.80]` | 0 | 0.6667 | narrower and wrong: expensive |
| `[0.10, 0.40]` | 1 | 0.7000 | confidently wrong |
| `0.75` (point) | 1 | 0.2500 | a confident hit |
| `[0.00, 1.00]` | either | 0.3333 | no information: the worst sharp forecaster |

The last row is the point of the scale: an interval `[0, 1]` costs exactly `1/3` whatever happens.
Any forecast that does worse than `1/3` was actively misleading.

### Why a proper score and not accuracy

Accuracy treats "0.51" and "0.99" as the same when they are right, and ignores the cost of being
confidently wrong. CRPS is strictly proper: the expected score is minimised by reporting the
distribution you actually believe, so **widening the band to hedge costs you, and narrowing it
without basis costs you**. That is the incentive a calibration ledger needs; the alternatives either
reward hedging (a per-entry "did the outcome fall inside the band" check, which for a binary outcome
is meaningless) or reward luck (accuracy).

## 2. Secondary: Brier at the midpoint

```
Brier = (m − y)²,   m = (l + u)/2
```

It is printed for familiarity and comparability with the literature. It never ranks the judgments:
it rewards a narrow band on its own and says nothing about whether the width was earned.

## 3. Murphy decomposition

With the forecast midpoints binned in ten bins, `N` judgments, bin `k` with `n_k` members, mean
forecast `f_k` and observed frequency `o_k`, and base rate `ō`:

```
REL = (1/N) Σ n_k (f_k − o_k)²      reliability  — lower is better
RES = (1/N) Σ n_k (o_k − ō)²        resolution   — higher is better
UNC = ō(1 − ō)                      uncertainty  — a property of the sample, not the forecaster
BS  = REL − RES + UNC
```

The identity holds exactly for the **binned** forecast (`bs_binned` in the report); the raw mean
Brier is printed next to it so the difference is visible instead of being hidden inside "≈". The
report prints the residual, which is `0` up to floating point.

## 4. Bands by declared width

A binary outcome can never fall inside a probability band: 0 and 1 are outside `[0.6, 0.9]` by
construction. So there is no per-entry "coverage" to count. What the report does instead is group
the resolved judgments by declared width and compare the **observed frequency** in that group with
the **average band declared** there:

| Width | n | Mean declared band | Observed frequency | Verdict |
|---|---|---|---|---|
| 0.10–0.30 | 17 | `[0.524, 0.724]` | 64.7% | inside |
| 0.00–0.10 | 8 | `[0.606, 0.606]` | 37.5% | **outside** |

The second row is the useful kind of failure: eight point forecasts around 0.6 resolved true only
three times. Groups with fewer than five judgments are flagged as insufficient.

## 5. Minimum sample

The curve and the decomposition are omitted, with exit code `3`, below **20 resolved judgments**.
Bins with fewer than five members are marked `†` and are indicative only. Both thresholds are
arguments (`--minimum-sample`), not constants buried in the code.
