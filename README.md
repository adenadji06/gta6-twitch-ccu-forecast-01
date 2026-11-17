# GTA VI Twitch CCU forecast — make.fun entry

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/adenadji06/gta6-twitch-ccu-forecast-01/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/adenadji06/gta6-twitch-ccu-forecast-01/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

Forecasts how many people watch Grand Theft Auto VI live on Twitch in each
hour of its release day, 2026-11-19 (UTC), from the first hour's print —
five quantiles an hour, scored by mean pinball loss on the log scale.

Entry for the make.fun bounty: https://make.fun/bounty/gta6-twitch-ccu-forecast-01

## Method

Shape forecaster, built at run time from the case's own comparables
(`main.py`, Python 3.13, standard library only, no network):

1. Anchor on hour 1's print. Each comparable launch contributes
   log(viewers_h / viewers_1) per hour; the median across comparables
   is the day's shape.
2. Only console-only launches shape the forecast — PC launches often
   unlock simultaneously at one global instant, so their UTC-day hour 1
   is pre-launch trickle and their ratios explode 100×; a console-only
   rolling-midnight launch is the true analogue of GTA VI.
3. Level tilt: launches whose hour 1 is already large grow less later
   in the day (console comparables' own regression: slope ≈ −0.32 at
   hour 19, ≈ 0 at hour 6). The median shape is shifted by
   −0.30 × (log p1 − ref) × ramp(h), ramp rising 0 → 1 from hour 6 to 19.
4. Spread per hour blends the cross-comparable dispersion (1.4826 × MAD
   of the log-ratios) with the house baseline's 0.15·√(h−1), clipped to
   [0.18, 0.95] log units. Falls back to all comparables, then to
   persistence, if the console set is too thin.

## Local practice validation

Practice answers fetched from SullyGnome (per the kit's `input/NOTICE.txt`):
Marvel's Wolverine, Red Dead Redemption 2, God of War Ragnarök,
Marvel's Spider-Man 2 — release-day hourly averages, hours 2–24.

| model | mean pinball loss | typical miss | 90% coverage |
|---|---|---|---|
| house baseline (starter) | 0.387 | 82.8% | 0.78 |
| this entry | **0.207** | **38.8%** | **0.88** |

Per case (this entry vs baseline): p00 0.353 vs 0.744, p01 0.179 vs 0.287,
p02 0.123 vs 0.215, p03 0.173 vs 0.303. Practice is graded on past
launches and pays nothing; it is no guide to the final.

## Run

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Reads every `*.in` in the input directory, writes `<id>.out` per case.
Deterministic (byte-identical repeat runs), under 1 s per practice case.
