# gta6-forecast

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/rickz19xx/gta6-forecast/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/rickz19xx/gta6-forecast/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)

An entry for make.fun's `gta6-twitch-ccu-forecast-01`: forecast how many people watch Grand
Theft Auto VI live on Twitch in each hour of its release day, 2026-11-19 (UTC), as five
quantiles an hour, scored by pinball loss on the log scale.

The program is `main.py` — Python 3.13, standard library only, one process, no network, no
randomness, no clock. It reads the single `<id>.in` case in `MAKEFUN_INPUT_DIR` and writes
`<id>.out` to `MAKEFUN_OUTPUT_DIR`:

```json
{"hours": [{"hour": 2, "q": [q05, q25, q50, q75, q95]}, ...]}
```

23 rows, hours 2..24, five finite non-decreasing numbers per row, above 0 and at most 1e9.

## The model

Hour 1's print (`known[0].viewers`, floored at 1) anchors the day. Each comparable launch
day is cut into its own 24 hourly values against its own `day_start`, and turned into a
log-ratio curve `log(max(viewers[h], 1) / viewers[0])` clipped to ±1.5. Then:

1. **Class** — keep the comparables whose hour 1 is at least 60% of their day's peak: they
   unlocked at or just before 00:00Z, which is GTA VI's situation (rolling midnight local,
   Europe already an hour in, US prime time). Fewer than five left relaxes the cut to 0.5,
   0.4, then keeps everything.
2. **Weights** — `exp(-0.8 * |log p1_c - log p1|)`: launches of a similar scale behave alike,
   and GTA VI is the biggest launch in the set.
3. **Pool** — per hour, the weighted quantiles at 0.05, 0.25, 0.5, 0.75, 0.95 (sort the
   ratios, walk the cumulative weight).
4. **Smooth** — a 3-hour moving average across each quantile, clamped at the day's ends.
5. **Emit** — row for hour H is hour index H-1: `p1 * exp(q)`, rounded half up to 2 decimals,
   clamped to [0.01, 1e9], forced non-decreasing within the row.

If nothing usable is left — no comparables, none with all 24 hours, a dead hour-1 print, a
truncated file — it degrades to persistence: every hour at hour 1's level with a random
walk's spread of `0.15 * sqrt(h-1)` in log. A malformed case still gets a valid file; an
invalid case wins nothing.

## Validation

Leave-one-out over the practice comparables in `p00.in` (37 usable of 38): each launch day
is held out, forecast from the other 36 with exactly the shipped code, and scored with the
competition's pinball loss on the log scale, hours 2..24.

| pool | model | house baseline |
|---|---|---|
| the 11 in-class launch days (hour-1 share ≥ 0.6) | **0.06991** | 0.12743 |
| the 16 launch days at share ≥ 0.5 (the reference lab's class) | 0.08462 | 0.12133 |

Model wins 9 of the 11 in-class days. Scoring the rounded numbers actually written to the
output file gives 0.06991 as well. The comparison is fair only inside the class: the model
predicts a launch that unlocked at 00:00Z, so scoring it on pre-midnight launches (hour 1 at
2% of the peak) inflates the loss — across all 37 days it is 0.53437 against the baseline's
0.46483.

`validate.py` also pushes six malformed cases (no comparables, broken timestamps, a
comparable with a gap, a zero hour-1 print, a 5e8 hour-1 print, no `known` block) through
`forecast_case` and checks the output contract on each: 23 rows, hours 2..24, five finite
non-decreasing numbers in range, 65536 bytes at most.

## Run it

```sh
# the grader's way, one case at a time
mkdir -p /tmp/in-p00 && cp input/p00.in /tmp/in-p00/
MAKEFUN_INPUT_DIR=/tmp/in-p00 MAKEFUN_OUTPUT_DIR=out python3 -P -s main.py

# every practice case
mkdir -p out && for c in p00 p01 p02 p03; do
  mkdir -p /tmp/in-$c && cp input/$c.in /tmp/in-$c/
  MAKEFUN_INPUT_DIR=/tmp/in-$c MAKEFUN_OUTPUT_DIR=out python3 -P -s main.py
done

# the leave-one-out self-check
python3 validate.py
```

`python3 -P -s` matches the grader: `-P` keeps the script's directory off `sys.path`, `-s`
drops user site-packages. `main.py` puts its own directory back first, so nothing else is
needed on the path. A run is one case, 0.1 s of work, and writes ~1.5 KB.

## Files

| file | what it is |
|---|---|
| `main.py` | the entry: reads the case, writes the forecast |
| `validate.py` | leave-one-out pinball check, contract check, malformed-case checks |
| `LICENSE` | MIT |
| `.makefun/owner.json` | the claim file: the wallet this entry belongs to |

Practice inputs come from the competition kit (`../gta6-twitch-ccu-forecast-01-kit`); they
are not copied here, and `validate.py` finds them there.
