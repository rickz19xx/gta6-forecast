"""gta6-twitch-ccu-forecast-01 — launch-day Twitch CCU forecaster (Python 3.13, stdlib only).

Reads the one case file in MAKEFUN_INPUT_DIR (default /input) and writes <id>.out to
MAKEFUN_OUTPUT_DIR (default /output):

    {"hours": [{"hour": 2, "q": [q05, q25, q50, q75, q95]}, ...]}

exactly 23 rows, hours 2..24, five finite non-decreasing numbers per row, > 0 and <= 1e9.

The model: hour 1's print anchors the day; each comparable launch day is turned into a
log-ratio curve against its own hour 1, restricted to the launches that unlocked at or
just before 00:00Z (hour 1 near the day's peak), weighted by how close its hour-1 scale
is to this launch's, and pooled into weighted quantiles that are smoothed over three
hours. Anything unusable falls back to persistence with a random-walk spread.

    mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
"""

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]
SIGMA = 0.15

HOURS = 24
HOUR = 3600.0
CLIP = 1.5
WEIGHT_SCALE = 0.8
CLASS_THRESHOLDS = (0.6, 0.5, 0.4)
# a launch whose day peaks at hour index >= PEAK_MIN and whose hour 1 is at most SHARE_MAX of the peak
PEAK_MIN = 12
SHARE_MAX = 0.6
CLASS_MIN = 5

Q_MIN = 0.01
Q_MAX = 1e9


# ---------------------------------------------------------------- input parsing

def _ts(value):
    """An ISO 8601 instant as an aware UTC datetime, or None if it is not one."""
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        stamp = datetime.fromisoformat(text)
    except (ValueError, TypeError):
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def _num(value):
    """A finite float from a JSON number or numeric string, else 0.0."""
    if isinstance(value, bool) or value is None:
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _viewers(point):
    if isinstance(point, dict):
        return max(_num(point.get("viewers")), 0.0)
    return 0.0


def hour_one(case):
    """Hour 1's print, floored at 1: the case's `known` row for hour 1, else its first row."""
    known = case.get("known")
    if not isinstance(known, list):
        return 1.0
    rows = [row for row in known if isinstance(row, dict)]
    first = next((row for row in rows if _num(row.get("hour")) == 1), None)
    if first is None:
        first = next((row for row in rows if "viewers" in row), None)
    if first is None:
        return 1.0
    return max(_num(first.get("viewers")), 1.0)


def build_curves(case):
    """Every comparable's 24-hour curve against its own day_start, hour index 0 = hour 1 of that day."""
    curves = []
    comparables = case.get("comparables")
    if not isinstance(comparables, list):
        return curves
    for comp in comparables:
        if not isinstance(comp, dict):
            continue
        start = _ts(comp.get("day_start"))
        points = comp.get("hourly")
        if start is None or not isinstance(points, list):
            continue
        values = {}
        for point in points:
            stamp = _ts(point.get("from")) if isinstance(point, dict) else None
            if stamp is None:
                continue
            offset = int(math.floor((stamp - start).total_seconds() / HOUR))
            if 0 <= offset < HOURS:
                values[offset] = _viewers(point)
        if len(values) < HOURS:
            continue
        first = values.get(0, 0.0)
        if first <= 0.0:
            continue
        peak = max(values.values())
        peak_hour = max(values, key=lambda k: (values[k], -k)) if values else 0
        curves.append({"vals": values, "p1": first, "share": first / peak if peak > 0 else 0.0,
                       "peak": peak_hour})
    return curves


# ---------------------------------------------------------------- the model

def pick_class(curves):
    """Launches whose day peaks in the afternoon/evening: their unlock left the US for later,
    which is this case's structure (rolling midnight local, the US arrives hours into the UTC day)."""
    kept = [c for c in curves if c.get("peak", 0) >= PEAK_MIN and c["share"] <= SHARE_MAX]
    if len(kept) >= CLASS_MIN:
        return kept
    for threshold in CLASS_THRESHOLDS:
        kept = [c for c in curves if c["share"] >= threshold]
        if len(kept) >= CLASS_MIN:
            return kept
    return list(curves)


def weights_for(kept, p1):
    """Closer hour-1 scale behaves alike; GTA VI is the biggest launch in the set."""
    if not kept:
        return []
    anchor = math.log(max(p1, 1.0))
    weights = []
    for c in kept:
        try:
            distance = abs(math.log(max(c["p1"], 1.0)) - anchor)
        except (ValueError, OverflowError):
            distance = 0.0
        weights.append(math.exp(-WEIGHT_SCALE * distance))
    return weights if sum(weights) > 0.0 else [1.0] * len(kept)


def weighted_quantile(pairs, tau):
    """pairs: (value, weight), value ascending. Walk the cumulative weight to tau of the total."""
    ordered = sorted(pairs, key=lambda pair: pair[0])
    total = sum(weight for _, weight in ordered)
    if total <= 0.0:
        return ordered[len(ordered) // 2][0]
    target = tau * total
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= target:
            return value
    return ordered[-1][0]


def ratio_at(curve, index):
    """log(hour's viewers / hour 1), floored at 1 viewer and clipped to +-1.5."""
    ratio = math.log(max(curve["vals"].get(index, 0.0), 1.0) / curve["p1"])
    return max(min(ratio, CLIP), -CLIP)


def persistence(p1):
    """Fallback: hour h draws what hour 1 drew, with a random walk's widening spread in log."""
    return [[z * SIGMA * math.sqrt(index) for z in Z] for index in range(HOURS)]


def forecast_logs(p1, curves):
    """24 rows of five log-ratio quantiles, or the persistence fallback if nothing is usable."""
    kept = pick_class(curves)
    if not kept:
        return persistence(p1)
    weights = weights_for(kept, p1)
    raw = []
    for index in range(HOURS):
        pairs = [(ratio_at(c, index), weight) for c, weight in zip(kept, weights)]
        raw.append([weighted_quantile(pairs, tau) for tau in LEVELS])
    smoothed = []
    for index in range(HOURS):
        before = raw[max(0, index - 1)]
        current = raw[index]
        after = raw[min(HOURS - 1, index + 1)]
        smoothed.append([(before[i] + current[i] + after[i]) / 3.0 for i in range(len(LEVELS))])
    return smoothed


# ---------------------------------------------------------------- output

def round2(value):
    """Rounded to 2 decimals, half up; a whole number comes back as an int."""
    scaled = value * 100.0
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    rounded = whole / 100.0
    return int(rounded) if float(rounded).is_integer() else rounded


def quantiles(p1, logs):
    """Five output numbers for one hour, clamped in range and non-decreasing by construction."""
    out = []
    previous = 0.0
    for qlog in logs:
        try:
            value = p1 * math.exp(qlog)
        except OverflowError:
            value = Q_MAX
        if not math.isfinite(value):
            value = Q_MAX
        value = min(max(value, Q_MIN), Q_MAX)
        value = max(value, previous)
        value = min(max(round2(value), Q_MIN), Q_MAX)
        if value < previous:
            value = previous
        out.append(value)
        previous = value
    return out


def forecast_case(case):
    p1 = hour_one(case)
    curves = build_curves(case)
    try:
        logs = forecast_logs(p1, curves)
    except Exception:
        logs = persistence(p1)
    rows = [{"hour": h, "q": quantiles(p1, logs[h - 1])} for h in range(2, 25)]
    return {"hours": rows}


def safe_forecast(case):
    """Never raise: a broken case still gets a valid persistence forecast."""
    try:
        return forecast_case(case)
    except Exception:
        p1 = 1.0
        try:
            p1 = hour_one(case)
        except Exception:
            pass
        return {"hours": [{"hour": h, "q": quantiles(p1, persistence(p1)[h - 1])} for h in range(2, 25)]}


# ---------------------------------------------------------------- entry point

def case_files(directory):
    """The case files there: <id>.in first, any other file as a last resort."""
    found = sorted(directory.glob("*.in"))
    if found:
        return found
    try:
        return sorted(p for p in directory.iterdir() if p.is_file() and p.suffix != ".out")
    except OSError:
        return []


def input_files():
    paths = case_files(INPUT_DIR)
    if not paths and INPUT_DIR != Path("/input"):
        paths = case_files(Path("/input"))
    return paths


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in input_files():
        case = {}
        try:
            case = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(case, dict):
                case = {}
        except Exception:
            case = {}
        forecast = safe_forecast(case)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
