# forecaster notes 01
# forecaster notes 02
# forecaster notes 03
# forecaster notes 04
# forecaster notes 05
# forecaster notes 06
# forecaster notes 07
# forecaster notes 08
# forecaster notes 09
# forecaster notes 10
# forecaster notes 11
# forecaster notes 12
# forecaster notes 13
# forecaster notes 14
# forecaster notes 15
# forecaster notes 16
# forecaster notes 17
# forecaster notes 18
# forecaster notes 19
# forecaster notes 20
# forecaster notes 21
# forecaster notes 22
# forecaster notes 23
# forecaster notes 24
# forecaster notes 25
# forecaster notes 26
# forecaster notes 27
# forecaster notes 28
# forecaster notes 29
# forecaster notes 30
#!/usr/bin/env python3
"""Quantile forecast of Twitch viewers (hours 2-24) on a log scale.

Each case file in MAKEFUN_INPUT_DIR (*.in, JSON) reports hour-1 viewers in its
"known" rows; that value anchors the curve. For hour h (2..24) and each of the
five normal quantiles z the forecast is

    q(h, z) = p1 * exp(SHAPE_WEIGHT * SHAPE[h-2] + z * SPREAD * sqrt(h-1))

rounded to two decimals, sorted ascending, clamped to [0.01, 1e9]. One .out
file per case lands in MAKEFUN_OUTPUT_DIR.

Standard library only, deterministic, no network.
"""

import json
import math
import os

# Five standard normal quantiles for levels 0.05, 0.25, 0.50, 0.75, 0.95.
Z_QUANTILES = (
    -1.6448536269514722,
    -0.6744897501960817,
    0.0,
    0.6744897501960817,
    1.6448536269514722,
)

# Launch-day shape, measured once from past launches (hours 2..24).
SHAPE = (
    -0.147, -0.258, -0.23, -0.002, 0.006, -0.027, -0.094, -0.116, -0.096,
    -0.024, 0.061, 0.167, 0.31, 0.341, 0.425, 0.464, 0.518, 0.541, 0.566,
    0.545, 0.544, 0.514, 0.51,
)

# Multiplier on SHAPE (the "A" of the formula). 0.0 => flat centre.
SHAPE_WEIGHT = 0.0
# Log-scale spread per sqrt(hour) (the "K" of the formula).
SPREAD = 0.06

FALLBACK_P1 = 1.0
LOW_CLAMP = 0.01
HIGH_CLAMP = 1e9


def hour_one_viewers(known):
    """Viewers reported for hour 1, or FALLBACK_P1 when missing/unreadable."""
    if not isinstance(known, list):
        return FALLBACK_P1
    for row in known:
        if not isinstance(row, dict):
            continue
        hour = row.get("hour")
        try:
            if int(hour) != 1:
                continue
        except (TypeError, ValueError):
            continue
        try:
            p1 = float(row.get("viewers"))
        except (TypeError, ValueError):
            return FALLBACK_P1
        if not math.isfinite(p1):
            return FALLBACK_P1
        return p1
    return FALLBACK_P1


def forecast(p1):
    """23 hours of five quantiles each, from the hour-1 anchor."""
    hours = []
    for hour in range(2, 25):
        shape = SHAPE[hour - 2]
        drift = SHAPE_WEIGHT * shape
        widen = SPREAD * math.sqrt(hour - 1)
        qs = []
        for z in Z_QUANTILES:
            value = p1 * math.exp(drift + z * widen)
            value = min(max(value, LOW_CLAMP), HIGH_CLAMP)
            qs.append(round(value, 2))
        qs.sort()
        hours.append({"hour": hour, "q": qs})
    return {"hours": hours}


def main():
    in_dir = os.environ["MAKEFUN_INPUT_DIR"]
    out_dir = os.environ["MAKEFUN_OUTPUT_DIR"]
    os.makedirs(out_dir, exist_ok=True)

    names = sorted(n for n in os.listdir(in_dir) if n.endswith(".in"))
    for name in names:
        with open(os.path.join(in_dir, name), "r", encoding="utf-8") as fh:
            case = json.load(fh)
        p1 = hour_one_viewers(case.get("known"))
        payload = forecast(p1)
        out_path = os.path.join(out_dir, name[:-3] + ".out")
        with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, separators=(",", ":"))
            fh.write("\n")


if __name__ == "__main__":
    main()
# quantile forecast v2
# revised: quantile pass 2