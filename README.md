# Polymarket FAA attribution forecast — v2

Forecasts the Yes price of every market of Polymarket's FAA outage
attribution family at every minute of the 4 hours after each checkpoint:
five quantiles (0.05, 0.25, 0.5, 0.75, 0.95) for minutes +1..+240.

## Method (v2)

Random walk around the last price, `q_tau(h) = clamp(x + z_tau * sigma *
h**0.43, 0, 1)`, with a per-market sigma estimated from that market's own
1-minute history:

- **EWMA variance** of 1-minute moves (half-life 90 minutes), each move
  winsorised at ±0.05. Recency weighting beats plain window averages:
  these prices move in bursts, and yesterday's calm says little about
  the next four hours.
- **Shrunk 50% toward the house baseline variance** (0.0025²) — a
  market's own history is noisy, especially for young markets.
- **Level factor** `sqrt(4*x*(1-x))`: a price near 0 or 1 cannot move
  as far as one near 0.5.
- **Young-market boost** `sqrt(1 + 100/n)`: a 20-minute-old market is
  far less predictable than a 3-day-old one.
- **Floor 0.0003, cap 0.05** on sigma.
- **Spread grows as h**0.43**, not sqrt(h): prices move in steps with
  long flat minutes, so the realised spread grows slower than a plain
  random walk's at first.
- **Median = last price, no drift.** Drift (last-hour slope, several
  weights) was tested on the practice cases and always made the
  pinball loss worse.
- **Symmetric normal quantiles.** Heavier-tailed (Student-t) sets and
  asymmetric upper/lower widths were tested and lost.

## What changed from v1

| | v1 | v2 |
|---|---|---|
| Volatility | mean of 24 h + 4 h window variances | EWMA, half-life 90 min |
| Shrink to baseline | 75% baseline (25% own) | 50% baseline (50% own) |
| Horizon growth | sqrt(h) | h**0.43 |
| Sigma floor | 0.0008 | 0.0003 |
| Young markets | no adjustment | sqrt(1 + 100/n) boost |
| Drift | none | none (retested, still worse) |

Ideas tested and rejected on the practice cases: Student-t
quantiles, asymmetric quantiles, per-quantile horizon exponents,
drift (any weight), logit-space random walk, MAD-based sigma,
empirical h-step quantiles, and a logit transform. Every rejected
idea scored worse than the v2 method above on the same six cases.

## Practice results (mean pinball loss x100, 6 cases)

| | mean | p00 | p01 | p02 | p03 | p04 | p05 |
|---|---|---|---|---|---|---|---|
| House baseline | 0.3636 | 0.5361 | 0.3804 | 0.4084 | 0.3686 | 0.2988 | 0.2382 |
| v1 | 0.2847 | 0.4510 | 0.3119 | 0.3403 | 0.2961 | 0.2137 | 0.1477 |
| **v2** | **0.2632** | 0.4537 | 0.3007 | 0.3471 | 0.2424 | 0.1884 | 0.1111 |

v2 beats v1 on four of six cases (p01, p03, p04, p05) and is within
0.007 on the other two (p00, p02). The practice is the NVIDIA-CEO
event, not the final's FAA markets, so the practice score is no guide
to the final; the method was chosen for being principled and
consistent across both halves of the practice, not for chasing the
last decimal.

## Run

Stdlib only, no network, deterministic (same input gives the same
output bytes). Reads every `*.in` in `$MAKEFUN_INPUT_DIR` (or
`/input/`) and writes one `<id>.out` per case to
`$MAKEFUN_OUTPUT_DIR` (or `/output/`):

```
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Runs in ~0.3 s per practice case on this machine, far under the
8-second sandbox limit.
