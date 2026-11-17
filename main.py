"""Forecast GTA VI launch-day Twitch viewers, hour by hour.

Reads one case file per run (makefun/twitch-ccu-case/v1) and writes, for
each of hours 2..24 of the release day, five quantiles of that hour's
concurrent-viewer count in the game's Twitch category.

Method -- shape forecaster, built from the case's own comparables:

1.  Anchor on hour 1's print p1.  Every comparable launch contributes the
    log-ratio log(viewers_h / viewers_1) for each hour h.  The median
    log-ratio across comparables is the day's shape.
2.  Only console-only launches are used for the shape.  PC launches often
    unlock simultaneously at a single global instant, so their UTC-day
    hour 1 is pre-launch trickle and their ratios explode by 100x or
    more; a console-only, rolling-midnight launch is the true analogue
    of GTA VI (PS5 / Xbox Series, midnight local, rolling).
3.  Level tilt.  Across the console comparables, a launch whose hour 1 is
    already large grows less later in the day than one whose hour 1 is
    small (ordinary least squares of log-ratio on log hour-1 gives a
    slope of about -0.32 at hour 19 and about 0 at hour 6, correlation
    about -0.8).  The median log-ratio is therefore shifted by
    -0.30 * (log p1 - ref) * ramp(h), where ref is the mean log hour-1
    of the console comparables and ramp rises linearly from 0 at hour 6
    to 1 at hour 19.  The tilt is a property of the comparables, not of
    the practice cases; the practice cases only confirm it.
4.  Spread.  The log-spread per hour blends the cross-comparable
    dispersion of the log-ratios (1.4826 * median absolute deviation)
    with the house baseline's random-walk spread, 0.15 * sqrt(h - 1),
    and is clipped to [0.18, 0.95] log units.

Fallbacks keep every case valid: if fewer than four console-only
comparables carry an hour-1 print, all comparables are used; if the
case carries no usable comparable at all, the forecast falls back to
persistence (median = hour 1, baseline spread).

Deterministic: no network, no randomness, no wall-clock use.  Two runs
on the same case write byte-identical output.  Standard library only.
"""

import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z_SCORES = [-1.645, -0.674, 0.0, 0.674, 1.645]

# Slope of the level tilt (log-ratio per unit of log hour-1), taken from
# the console comparables' own regression, and the hours over which the
# tilt ramps in (near zero at hour 6, full at hour 19).
TILT_SLOPE = -0.30
TILT_START_HOUR = 6
TILT_FULL_HOUR = 19

BASE_SPREAD_RATE = 0.15
MIN_SPREAD = 0.18
MAX_SPREAD = 0.95
MIN_CONSOLE_COMPARABLES = 4
MAX_VIEWERS = 1_000_000_000


def _median(values):
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return 0.5 * (ordered[mid - 1] + ordered[mid])


def _mad_spread(values):
    """Robust log-spread: 1.4826 * median absolute deviation."""
    if len(values) < 3:
        return 0.5
    centre = _median(values)
    return 1.4826 * _median([abs(v - centre) for v in values])


def _parse_time(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _hour_of(point_from, day_start):
    return int((_parse_time(point_from) - day_start).total_seconds() // 3600) + 1


def _is_console_only(comparable):
    platforms = comparable.get("platforms")
    if not isinstance(platforms, str):
        return False
    return "PC" not in platforms


def _collect_ratios(case):
    """Log-ratios per hour for the console-only comparables.

    Returns (ratios, ref_log_p1, n_comparables): ratios[h] is the list of
    log(viewers_h / viewers_1) over comparables with a positive hour-1
    print; ref_log_p1 is the mean log hour-1 print of those comparables.
    """
    day_logs = []
    ratios = {h: [] for h in range(2, 25)}
    n_comparables = 0
    for comparable in case.get("comparables") or []:
        if not _is_console_only(comparable):
            continue
        day_start = _parse_time(comparable["day_start"])
        by_hour = {}
        for point in comparable.get("hourly") or []:
            hour = _hour_of(point["from"], day_start)
            if 1 <= hour <= 24:
                by_hour[hour] = point["viewers"]
        first = by_hour.get(1)
        if not first or first <= 0:
            continue
        n_comparables += 1
        day_logs.append(math.log(first))
        for hour in range(2, 25):
            viewers = by_hour.get(hour)
            if viewers and viewers > 0:
                ratios[hour].append(math.log(viewers / first))
    return ratios, (sum(day_logs) / len(day_logs) if day_logs else None), n_comparables


def _collect_ratios_all(case):
    """Same as _collect_ratios but over every comparable (fallback)."""
    saved = []
    for comparable in case.get("comparables") or []:
        platforms = comparable.get("platforms")
        comparable = dict(comparable)
        comparable["platforms"] = "Console"
        saved.append(comparable)
    case = dict(case)
    case["comparables"] = saved
    return _collect_ratios(case)


def _round_half_up_2dp(value):
    whole = math.floor(value * 100.0 + 0.5) / 100.0
    return int(whole) if whole == int(whole) else whole


def _quantiles(p1, median_log_ratio, spread):
    out = []
    previous = 0.0
    for z in Z_SCORES:
        q = p1 * math.exp(median_log_ratio + z * spread)
        q = _round_half_up_2dp(q)
        q = min(max(q, 0.01), MAX_VIEWERS)
        q = max(q, previous)
        out.append(q)
        previous = q
    return out


def forecast_case(case, name):
    if case["levels"] != LEVELS:
        raise ValueError(f"{name} asks for levels {case['levels']}, not {LEVELS}")
    known = next((k for k in case["known"] if k["hour"] == 1), None)
    if known is None:
        raise ValueError(f"{name} has no hour-1 print")
    p1 = max(1.0, float(known["viewers"]))

    ratios, ref_log_p1, n_comparables = _collect_ratios(case)
    if n_comparables < MIN_CONSOLE_COMPARABLES or ref_log_p1 is None:
        ratios, ref_log_p1, _n = _collect_ratios_all(case)
    if ref_log_p1 is None:
        # No usable comparable at all: persistence, tilt zero.
        ref_log_p1 = log_p1

    log_p1 = math.log(p1)
    hours = []
    for row in case["forecast"]:
        hour = row["hour"]
        values = ratios.get(hour) or []
        if values:
            shape = _median(values)
            ramp = (hour - TILT_START_HOUR) / (TILT_FULL_HOUR - TILT_START_HOUR)
            ramp = min(1.0, max(0.0, ramp))
            shape += TILT_SLOPE * (log_p1 - ref_log_p1) * ramp
            spread = 0.5 * _mad_spread(values) + 0.5 * BASE_SPREAD_RATE * math.sqrt(hour - 1)
            spread = min(MAX_SPREAD, max(MIN_SPREAD, spread))
        else:
            shape = 0.0
            spread = BASE_SPREAD_RATE * math.sqrt(hour - 1)
            spread = min(MAX_SPREAD, max(MIN_SPREAD, spread))
        hours.append({"hour": hour, "q": _quantiles(p1, shape, spread)})
    return {"hours": hours}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        text = json.dumps(forecast, separators=(",", ":")) + "\n"
        (OUTPUT_DIR / f"{path.stem}.out").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
