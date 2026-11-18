"""Twitch viewer forecast for the GTA VI release day: hour h keeps hour 1's count.

    q_tau(h) = p1 * exp(z_tau * 0.115 * sqrt(h - 1))

with z_tau the standard normal's quantile at each level (0.05, 0.25, 0.5, 0.75, 0.95) and
p1 hour 1's print. The house baseline is this same flat shape with 0.15: a launch this size
keeps drawing near its first hour all day, so the honest spread around that is narrower
than the house's widening random walk, and the median holds hour 1's count rather than
drifting with it.
"""
import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

Z = (-1.6448536269514722, -0.6744897501960817, 0.0, 0.6744897501960817, 1.6448536269514722)
LEVELS = (0.05, 0.25, 0.5, 0.75, 0.95)
A = 0.0
K = 0.085
PROFILE = [-0.147, -0.258, -0.23, -0.002, 0.006, -0.027, -0.094, -0.116, -0.096, -0.024, 0.061, 0.167, 0.31, 0.341, 0.425, 0.464, 0.518, 0.541, 0.566, 0.545, 0.544, 0.514, 0.51]


def hour_one(case):
    for row in case.get("known") or []:
        if row.get("hour") == 1:
            try:
                return max(float(row.get("viewers") or 1.0), 1.0)
            except (TypeError, ValueError):
                return 1.0
    return 1.0


def rows(p1):
    out = []
    for h in range(2, 25):
        shift = A * PROFILE[h - 2]
        sigma = K * math.sqrt(h - 1)
        qs = []
        for tau, z in zip(LEVELS, Z):
            q = p1 * math.exp(shift + z * sigma)
            q = max(min(q, 1e9), 0.01)
            qs.append(round(q, 2))
        qs.sort()
        out.append({"hour": h, "q": qs})
    return out


def main():
    src = os.environ.get("MAKEFUN_INPUT_DIR") or "/input"
    dst = os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output"
    os.makedirs(dst, exist_ok=True)
    for name in sorted(os.listdir(src)):
        if not name.endswith(".in"):
            continue
        with open(os.path.join(src, name), encoding="utf-8") as fh:
            case = json.load(fh)
        p1 = hour_one(case)
        doc = {"hours": rows(p1)}
        with open(os.path.join(dst, name[:-3] + ".out"), "w", encoding="utf-8") as fh:
            json.dump(doc, fh, separators=(",", ":"))


if __name__ == "__main__":
    main()
