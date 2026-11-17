#!/usr/bin/env python3
"""validate.py — leave-one-out check of the entry's model over the practice comparables.

Reads p00.in from the kit, holds out each comparable launch day, forecasts it from the
rest with exactly the code main.py ships, and scores the five quantiles with the
competition's pinball loss on the log scale. Also checks the output contract on every
practice case and pushes malformed cases through the fallback path.

    python3 validate.py                     # kit's p00.in
    python3 validate.py path/to/case.in
"""

import json
import math
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import main

LEVELS = main.LEVELS
KIT_CASE = Path(__file__).resolve().parent.parent / "gta6-twitch-ccu-forecast-01-kit" / "input" / "p00.in"
CLASS = 0.6


def pinball(predicted, truth):
    total = 0.0
    for tau, quantile in zip(LEVELS, predicted):
        delta = truth - quantile
        total += max(tau * delta, (tau - 1.0) * delta)
    return total / len(LEVELS)


def baseline(p1):
    """The house baseline: hour h = hour 1, spread 0.15*sqrt(h-1) in log."""
    return main.persistence(p1)


def score(logs, values, p1, emitted=False):
    losses = []
    for index in range(1, main.HOURS):
        truth_viewers = values.get(index, 0.0)
        if truth_viewers <= 0.0:
            continue
        if emitted:
            predicted = [math.log(q / p1) for q in main.quantiles(p1, logs[index])]
        else:
            predicted = logs[index]
        losses.append(pinball(predicted, math.log(truth_viewers / p1)))
    return sum(losses) / len(losses) if losses else float("nan")


def leave_one_out(curves):
    in_class = []
    rows = []
    for held in curves:
        train = [c for c in curves if c is not held]
        logs = main.forecast_logs(held["p1"], train)
        model = score(logs, held["vals"], held["p1"])
        house = score(baseline(held["p1"]), held["vals"], held["p1"])
        rows.append((held, model, house))
        if held["share"] >= CLASS:
            in_class.append((held, model, house))
    return rows, in_class


def contract(case):
    out = main.forecast_case(case)
    hours = out["hours"]
    assert len(hours) == 23, "row count"
    assert [row["hour"] for row in hours] == list(range(2, 25)), "hour sequence"
    assert set(out) == {"hours"}, "keys"
    for row in hours:
        q = row["q"]
        assert len(q) == 5, "five quantiles"
        for value in q:
            assert isinstance(value, (int, float)) and not isinstance(value, bool), "numeric"
            assert math.isfinite(value), "finite"
            assert 0 < value <= 1e9, "range"
        assert all(q[i] <= q[i + 1] for i in range(4)), f"non-decreasing at hour {row['hour']}"
    size = len(json.dumps(out, separators=(",", ":")) + "\n")
    assert size <= 65536, "size"
    return size


def weird_cases(case):
    """Every shape of bad data the entry must survive, each still producing a valid forecast."""
    empty = {"schema": "", "known": [], "forecast": [], "comparables": []}
    broken = {
        "known": [{"hour": 1, "viewers": 0}],
        "comparables": [
            {"day_start": None, "hourly": None},
            {"day_start": "2020-01-01T00:00:00Z", "hourly": [{"from": "nope", "viewers": "x"}]},
            {"day_start": "2020-01-01T00:00:00Z", "hourly": [], "extra": {"ignored": True}},
        ],
        "extra_unknown_key": 12345,
    }
    few = {
        "known": [{"hour": 1, "viewers": 10}],
        "comparables": [case["comparables"][0], case["comparables"][1]],
    }
    gap = json.loads(json.dumps(case))
    gap["comparables"][0]["hourly"] = gap["comparables"][0]["hourly"][:5]
    zero_first = json.loads(json.dumps(case))
    for point in zero_first["comparables"][0]["hourly"]:
        if point["from"] == zero_first["comparables"][0]["day_start"]:
            point["viewers"] = 0
    huge = json.loads(json.dumps(case))
    huge["known"] = [{"hour": 1, "viewers": 5e8}]
    missing_known = {"comparables": case["comparables"], "forecast": []}
    return {
        "empty": empty,
        "broken": broken,
        "few comparables": few,
        "one comparable with a gap": gap,
        "zero hour-1 print": zero_first,
        "huge hour-1 print": huge,
        "no known block": missing_known,
    }


def main_():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else KIT_CASE
    case = json.loads(path.read_text(encoding="utf-8"))
    curves = main.build_curves(case)
    print(f"case            {path.name}")
    print(f"comparables     {len(curves)} usable of {len(case.get('comparables') or [])}")
    print(f"in class        {sum(1 for c in curves if c['share'] >= CLASS)} (hour-1 share >= {CLASS})")

    rows, in_class = leave_one_out(curves)
    model = sum(r[1] for r in in_class) / len(in_class)
    house = sum(r[2] for r in in_class) / len(in_class)
    wins = sum(1 for _, m, h in in_class if m < h)
    print()
    print(f"leave-one-out, {len(in_class)} in-class launch days")
    print(f"  model pinball mean   {model:.5f}")
    print(f"  house pinball mean   {house:.5f}")
    print(f"  model wins           {wins}/{len(in_class)}")
    emitted = [r for r in in_class]
    via_output = sum(score(main.forecast_logs(r[0]["p1"], [c for c in curves if c is not r[0]]),
                           r[0]["vals"], r[0]["p1"], emitted=True) for r in emitted) / len(emitted)
    print(f"  same loss through the emitted, rounded quantiles: {via_output:.5f}")
    print()
    all_model = sum(r[1] for r in rows) / len(rows)
    all_house = sum(r[2] for r in rows) / len(rows)
    print(f"all {len(rows)} comparables (out-of-class launches included): "
          f"model {all_model:.5f} vs house {all_house:.5f}")

    print()
    sizes = []
    for name, weird in weird_cases(case).items():
        size = contract(weird)
        sizes.append(size)
        print(f"  valid forecast  {name:<28} {size:>5} bytes")
    print()
    print(f"practice case   {contract(case)} bytes")


if __name__ == "__main__":
    main_()
