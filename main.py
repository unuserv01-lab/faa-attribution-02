#!/usr/bin/env python3
"""Forecast Polymarket FAA outage attribution prices, 4 hours ahead (v2).

For each market of a case, forecasts five quantiles (0.05, 0.25, 0.5, 0.75,
0.95) of the Yes price at every minute of the 240 minutes after the
checkpoint, as a random walk around the last price:

    q_tau(h) = clamp(x + z_tau * sigma * h**0.43, 0, 1), rounded to 6 dp

where x is the price at the checkpoint and sigma is a per-market spread
in price units, estimated from the market's own 1-minute history:

  * EWMA variance of 1-minute moves (half-life 90 minutes), each move
    winsorised at +/-0.05 so a single jump cannot dominate. Recency
    weighting beats plain window averages on the practice cases: these
    prices move in bursts, and yesterday's calm says little about the
    next four hours.
  * Shrunk 50% of the way toward the house baseline variance
    (0.0025^2). A market's own history is noisy, especially for young
    markets, and the baseline is a sane prior.
  * Scaled by sqrt(4*x*(1-x)), the level factor of a price that must
    stay inside [0, 1]: a market at 0.02 can barely move, one at 0.5
    can move freely.
  * A young-market boost, sqrt(1 + 100/n), widens the spread when the
    market has few prices so far: a 20-minute-old market is far less
    predictable than a 3-day-old one.
  * Floored at 0.0003 and capped at 0.05.

The spread grows as h**0.43, not sqrt(h): prices move in steps with
long flat minutes, so the realised spread grows slower than a plain
random walk's at first. The median stays at the last price: drift was
tested on the practice cases (last-hour slope, several weights) and
always made the pinball loss worse, so no drift is used. Symmetric
normal quantiles were tested against heavier-tailed (Student-t) ones
and against asymmetric upper/lower widths; the plain normal set won.

Practice pinball loss (mean x100): v2 0.2632 vs v1 0.2847 vs house
baseline 0.3636. The practice is the NVIDIA-CEO event, not the final's
FAA markets, so the practice score is no guide to the final; the
method was chosen for being principled and consistent across both
halves of the practice (early cases and late cases), not for chasing
the last decimal.

Stdlib only, no network, deterministic: the same input always gives
the same output bytes. Reads every *.in in $MAKEFUN_INPUT_DIR (or
/input/) and writes one <id>.out per case to $MAKEFUN_OUTPUT_DIR
(or /output/).
"""

import json
import math
import os

INPUT_DIR = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
OUTPUT_DIR = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")

QUANTILES = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.644854, -0.67449, 0.0, 0.67449, 1.644854]

BASE_SIGMA = 0.0025       # house baseline spread (price units / sqrt(min))
HALFLIFE = 90.0           # EWMA half-life in minutes for move variance
SHRINK = 0.5              # weight on the market's own variance estimate
CLIP = 0.05               # winsorise 1-minute moves at +/-CLIP
ALPHA = 0.43              # spread grows as h**ALPHA (sub-diffusive steps)
SIGMA_FLOOR = 0.0003
SIGMA_CAP = 0.05
YOUNG_K = 100.0           # young-market boost: sqrt(1 + YOUNG_K / n)


def price6(x):
    """x clamped to [0, 1] and rounded to 6 decimals (0, never -0)."""
    v = round(min(1.0, max(0.0, x)) * 1e6) / 1e6
    return v + 0.0


def ewma_var(prices):
    """Recency-weighted mean squared 1-minute move.

    Moves are winsorised at +/-CLIP so one jump (the FAA family has
    seen 0.49 -> 0.275 in one minute) cannot dominate. Weights decay
    by half every HALFLIFE minutes, newest first. Returns 0 when
    fewer than two prices are available.
    """
    n = len(prices)
    if n < 2:
        return 0.0
    decay = 0.5 ** (1.0 / HALFLIFE)
    weight = 1.0
    wsum = 0.0
    total = 0.0
    for i in range(n - 1, 0, -1):
        d = prices[i] - prices[i - 1]
        if d > CLIP:
            d = CLIP
        elif d < -CLIP:
            d = -CLIP
        total += weight * d * d
        wsum += weight
        weight *= decay
    return total / wsum


def market_sigma(prices):
    """Per-market spread in price units."""
    x = prices[-1] if prices else 0.5
    var = ewma_var(prices)
    var = SHRINK * var + (1.0 - SHRINK) * BASE_SIGMA * BASE_SIGMA
    sigma = math.sqrt(var)
    # A price near 0 or 1 cannot move as far as one near 0.5.
    sigma *= math.sqrt(4.0 * max(x * (1.0 - x), 1e-6))
    # A young market is less predictable than an old one.
    sigma *= math.sqrt(1.0 + YOUNG_K / max(len(prices), 1))
    if sigma < SIGMA_FLOOR:
        sigma = SIGMA_FLOOR
    elif sigma > SIGMA_CAP:
        sigma = SIGMA_CAP
    return sigma


def forecast(prices, horizon):
    """240 rows of five quantiles around the market's last price."""
    if not prices:
        x = 0.5
    else:
        x = min(1.0, max(0.0, prices[-1]))
    sigma = market_sigma(prices) if prices else BASE_SIGMA
    rows = []
    for h in range(1, horizon + 1):
        spread = sigma * (h ** ALPHA)
        rows.append([price6(x + z * spread) for z in Z])
    return rows


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    inputs = sorted(f for f in os.listdir(INPUT_DIR) if f.endswith(".in"))
    for name in inputs:
        case_id = name[:-3]
        with open(os.path.join(INPUT_DIR, name), "r", encoding="utf-8") as fh:
            case = json.load(fh)
        horizon = int(case.get("horizon_minutes", 240))
        quantiles = case.get("quantiles", QUANTILES)
        if len(quantiles) != len(QUANTILES) or any(
            q != t for q, t in zip(quantiles, QUANTILES)
        ):
            raise ValueError(
                "%s asks for quantiles %r, not %r" % (name, quantiles, QUANTILES)
            )
        forecasts = []
        for market in case["markets"]:
            forecasts.append(
                {"id": market["id"], "q": forecast(market["prices"], horizon)}
            )
        out = json.dumps({"forecasts": forecasts}, separators=(",", ":")) + "\n"
        with open(
            os.path.join(OUTPUT_DIR, case_id + ".out"), "w", encoding="utf-8"
        ) as fh:
            fh.write(out)


if __name__ == "__main__":
    main()
