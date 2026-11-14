# faa-attribution-02 — Polymarket FAA outage attribution forecaster

Forecasts the Yes price of every market of Polymarket's FAA outage
attribution family at every minute of the 4 hours after a checkpoint:
five quantiles (0.05, 0.25, 0.5, 0.75, 0.95) per market per minute.

## How it works

For each market, a random walk around its last price:

    q_tau(h) = clamp(x + z_tau * sigma * sqrt(h), 0, 1)

with `sigma` estimated per market from its own 1-minute history:

- variance of 1-minute moves over the last 24 h and the last 4 h
  (mean of the two), each move winsorised at ±0.05 so a single jump
  cannot dominate the estimate;
- shrunk 25% of the way toward the house baseline variance
  (0.0025²), because 72 h of history is far jumpier than the next
  4 h and the estimate is noisy for young markets;
- scaled by sqrt(4·x·(1−x)): a price near 0 or 1 cannot move as far
  as one near 0.5;
- floored at 0.0008, capped at 0.05.

The median stays at the last price (no drift: a damped last-hour
trend was tested on the practice cases and only made the pinball
loss worse).

## Practice score (local, against Polymarket history)

- House baseline: pinball loss **0.363589**
- This entry: pinball loss **≈0.285**, 90% coverage ≈0.94

Practice is the "Next CEO of NVIDIA?" event, not the FAA family, so
it is no guide to the final — the method was kept simple and robust
rather than tuned to the practice's exact optimum.

## Run

```sh
mkdir -p out
MAKEFUN_INPUT_DIR=<kit>/input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Stdlib only, no network, deterministic (two runs are byte-identical).
Reads every `*.in` in the input dir, writes one `<id>.out` per case.
