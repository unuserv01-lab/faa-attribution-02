# Polymarket FAA attribution forecast — v3

Forecasts the Yes price of every market of Polymarket's FAA outage
attribution family at every minute of the 4 hours after each checkpoint:
five quantiles (0.05, 0.25, 0.5, 0.75, 0.95) for minutes +1..+240.

## Method (unchanged from v2)

Random walk around the last price, `q_tau(h) = clamp(x + z_tau * sigma *
h**0.43, 0, 1)`, with a per-market sigma estimated from that market's own
1-minute history:

- **EWMA variance** of 1-minute moves (half-life 90 minutes), each move
  winsorised at ±0.05.
- **Shrunk 50% toward the house baseline variance** (0.0025²).
- **Level factor** `sqrt(4*x*(1-x))`.
- **Young-market boost** `sqrt(1 + 100/n)`.
- **Floor 0.0003, cap 0.05** on sigma.
- **Spread grows as h**0.43**, not sqrt(h).
- **Median = last price, no drift.**

No parameter, formula, or behaviour of the normal forecast changed
from v2. See the v2 README for the full method and the ideas tested
and rejected on the practice cases.

## What changed from v2: robustness only

v2 raised an exception and died if a case was malformed — one bad
case (for example a quantiles list that is not the standard five)
would stop every case after it from being written, and any invalid
case takes no prize. v3 keeps the exact same forecast math and adds
guards so a malformed input degrades instead of crashing:

- **Per-market guard** (`forecast_market`): the normal v2 forecast
  runs first. If it raises for a market (missing `prices`, wrong
  type, non-numeric values), only that market falls back to the
  house baseline forecast (`q = x + z_tau * 0.0025 * sqrt(h)`,
  x = last usable price, else 0.5). The other markets are untouched.
- **Per-case guard** (`process_case`): a case that cannot be parsed
  as JSON, has a bad horizon, asks for different quantiles, or has
  a missing/malformed markets list falls back to baseline forecasts
  for every market it lists, writes its output, and processing
  continues with the next case. A case file that is not valid JSON
  still gets an (empty) output file so the run completes.
- The fallback **only runs when an exception is raised**. On every
  well-formed case the output is byte-identical to v2 (verified
  below).

## Practice results (mean pinball loss x100, 6 cases)

| | mean | p00 | p01 | p02 | p03 | p04 | p05 |
|---|---|---|---|---|---|---|---|
| House baseline | 0.3636 | 0.5361 | 0.3804 | 0.4084 | 0.3686 | 0.2988 | 0.2382 |
| v2 | 0.2632 | 0.4537 | 0.3007 | 0.3471 | 0.2424 | 0.1884 | 0.1111 |
| **v3** | **0.2632** | 0.4537 | 0.3007 | 0.3471 | 0.2424 | 0.1884 | 0.1111 |

v3 scores exactly the same as v2 on the practice (per case and in
total), because the fallback never fires there. The practice is the
NVIDIA-CEO event, not the final's FAA markets, so the practice score
is no guide to the final.

## Fallback test (deliberately corrupted input)

A test input directory was built with: p00 intact; p01 with one
market's prices replaced by a string value and another market
missing `prices` entirely; p02 with a wrong quantiles list;
p03 as invalid JSON; p04 and p05 intact. v3 wrote a valid output
for every case (240 rows × 5 quantiles, monotone, in [0, 1]),
used the baseline forecast for the two broken markets of p01 and
for all markets of p02, wrote an empty forecasts list for p03,
and produced byte-identical outputs for the intact cases p00, p04
and p05. v2 run on the same directory raised `ValueError` on p02
and wrote nothing after it.

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
