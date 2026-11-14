#!/usr/bin/env python3
"""Forecast Polymarket FAA outage attribution prices, 4 hours ahead.

For each market of a case, forecasts five quantiles (0.05, 0.25, 0.5, 0.75,
0.95) of the Yes price at every minute of the 240 minutes after the
checkpoint, as a random walk around the last price:

    q_tau(h) = clamp(x + z_tau * sigma * sqrt(h), 0, 1), rounded to 6 dp

where x is the price at the checkpoint and sigma is a per-market spread
in price units per square-root minute, estimated from the market's own
1-minute history:

  * variance of 1-minute moves over the last 24 h and the last 4 h
    (mean of the two), each move winsorised at +/-0.05 so one jump
    cannot dominate the estimate;
  * shrunk 25% of the way toward the house baseline variance
    (0.0025^2), because a market's 72 h history is far jumpier than
    its next 4 h, and the estimate is noisy for young markets;
  * scaled by sqrt(4*x*(1-x)), the level factor of a price that must
    stay inside [0, 1]: a market at 0.02 can barely move, one at 0.5
    can move freely;
  * floored at 0.0008 and capped at 0.05.

The median stays at the last price: the last hour's slope was tested
on the practice cases and a damped drift only made the pinball loss
worse, so no drift is used.

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
SHRINK = 0.25             # weight on the market's own variance estimate
CLIP = 0.05               # winsorise 1-minute moves at +/-CLIP
LONG_WIN = 1440           # minutes of history for the long variance (24 h)
SHORT_WIN = 240           # minutes of history for the short variance (4 h)
SIGMA_FLOOR = 0.0008
SIGMA_CAP = 0.05


def price6(x):
    """x clamped to [0, 1] and rounded to 6 decimals (0, never -0)."""
    v = round(min(1.0, max(0.0, x)) * 1e6) / 1e6
    return v + 0.0


def window_var(prices, window):
    """Mean squared 1-minute move over the last `window` minutes.

    Moves are winsorised at +/-CLIP so a single jump (the FAA family
    has seen 0.49 -> 0.275 in one minute) cannot dominate. Returns 0
    when fewer than two prices are available.
    """
    m = prices[-window:] if window < len(prices) else prices
    n = len(m) - 1
    if n <= 0:
        return 0.0
    total = 0.0
    for i in range(1, len(m)):
        d = m[i] - m[i - 1]
        if d > CLIP:
            d = CLIP
        elif d < -CLIP:
            d = -CLIP
        total += d * d
    return total / n


def market_sigma(prices):
    """Per-market spread in price units per square-root minute."""
    x = prices[-1] if prices else 0.5
    var = 0.5 * (window_var(prices, LONG_WIN) + window_var(prices, SHORT_WIN))
    var = SHRINK * var + (1.0 - SHRINK) * BASE_SIGMA * BASE_SIGMA
    sigma = math.sqrt(var)
    # A price near 0 or 1 cannot move as far as one near 0.5.
    sigma *= math.sqrt(4.0 * max(x * (1.0 - x), 1e-6))
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
        spread = sigma * math.sqrt(h)
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
