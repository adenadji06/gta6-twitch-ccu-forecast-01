# GTA VI Twitch CCU forecast — make.fun entry

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/adenadji06/gta6-twitch-ccu-forecast-01/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/adenadji06/gta6-twitch-ccu-forecast-01/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

Forecasts how many people watch Grand Theft Auto VI live on Twitch in each
hour of its release day, 2026-11-19 (UTC), from the first hour's print —
five quantiles an hour, scored by mean pinball loss on the log scale.

Entry for the make.fun bounty: https://make.fun/bounty/gta6-twitch-ccu-forecast-01

## Method

Two shape estimators, blended 50/50 in log space, both fitted at run time
from the case's own comparables (`main.py`, Python 3.13, standard library
only, no network):

1. **Console median.** Only console-only launches (no PC in their
   platforms) enter the shape — a PC launch often unlocks at one global
   instant, so its UTC-day hour 1 is pre-launch trickle and its ratios
   explode; a console launch unlocks at midnight local, rolling, the true
   analogue of GTA VI (PS5 / Xbox Series). The shape is the median
   log-ratio log(viewers_h / viewers_1) per hour, tilted by the level
   effect (a launch that opens big grows less later: tilt −0.30 ×
   (log p1 − ref), ramped in from hour 6 to hour 19). Spread blends the
   cross-comparable dispersion (1.4826 × MAD) with the house baseline's
   0.15·√(h−1), clipped to [0.18, 0.95].
2. **Level regression.** Over every comparable with a full 24-hour release
   day and hour 1 ≥ 5,000 viewers, each hour's log-ratio is regressed on
   log hour-1 by least squares, and the case's median is read off that
   line at its own hour-1 print (winsorised to the pool's observed range,
   so an hour-1 above anything seen before is treated like the biggest
   observed launch). Spread is the regression's residual standard
   deviation per hour, floored at 0.15.

The final median is the mean of the two arms' log-medians, the final spread
the mean of their spreads. Fallbacks: the median arm uses all comparables
when the console pool is thinner than four; the regression arm falls back to
persistence when its pool is thinner than five; with no usable comparable at
all the forecast is the flat house baseline.

## Local practice validation

Practice answers fetched from SullyGnome (per the kit's `input/NOTICE.txt`,
"Average viewers" dataset): Marvel's Wolverine, Red Dead Redemption 2, God
of War Ragnarök, Marvel's Spider-Man 2 — release-day hourly averages,
hours 2–24. A leave-one-out test over the 29 usable comparables
(hour 1 ≥ 5,000) uses each launch as a pseudo-case, shape fitted from the
other 28.

| model | practice mean pinball loss | LOO mean pinball loss |
|---|---|---|
| house baseline (starter) | 0.387 | 0.360 |
| this entry (blend) | **0.207** | **0.254** |

Per practice case (this entry vs baseline): p00 0.322 vs 0.744, p01 0.193
vs 0.287, p02 0.134 vs 0.215, p03 0.181 vs 0.303. Practice is graded on
past launches and pays nothing; it is no guide to the final.

## Run

```sh
cd gta6-twitch-ccu-forecast-01-kit
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 ../gta6-twitch-ccu-forecast-01-entry/main.py
```

Reads every `*.in` in the input directory, writes `<id>.out` per case.
Deterministic (byte-identical repeat runs), under 1 s per practice case.
