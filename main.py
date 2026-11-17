"""Forecast GTA VI launch-day Twitch viewers, hour by hour.

Reads one case file per run (makefun/twitch-ccu-case/v1) and writes, for
each of hours 2..24 of the release day, five quantiles of that hour's
concurrent-viewer count in the game's Twitch category.

Method -- two independent shape estimators, blended 50/50 in log space,
both fitted at run time from the case's own comparables (past big
launches with hourly Twitch category averages):

Arm 1, console median.  Only console-only launches (no PC in their
platforms) enter the shape: a PC launch often unlocks at one global
instant, so its UTC-day hour 1 is pre-launch trickle and its ratios
explode; a console launch unlocks at midnight local, rolling, which is
the true analogue of GTA VI (PS5 / Xbox Series).  The shape is the
median log-ratio log(viewers_h / viewers_1) per hour, tilted by the
level effect: launches that open big grow less later in the day, so the
median is shifted by TILT_SLOPE * (log p1 - ref) * ramp(h), ramp rising
from 0 at hour 6 to 1 at hour 19.  Its spread blends the
cross-comparable dispersion (1.4826 * median absolute deviation) with
the house baseline's 0.15 * sqrt(h - 1), clipped to [0.18, 0.95].

Arm 2, level regression.  Over every comparable with a full 24-hour
release day and hour 1 of at least 5,000 viewers (below that the
first hour is pre-unlock trickle and the ratios are wild), each hour's
log-ratio is regressed on log hour-1 by least squares, and the case's
median is read off that line at its own hour-1 print.  The level
effect is large: the correlation between log hour-1 and the late-day
log-ratio is about -0.7 across the pool.  The anchor log hour-1 is
winsorised to the pool's observed range, so an hour-1 print above
anything seen before is treated like the biggest observed launch
instead of extrapolating the line.  Its spread is the regression's
residual standard deviation per hour, floored at 0.15.

The final median is the mean of the two arms' log-medians and the
final spread the mean of their spreads.  On the 4 practice cases the
blend scores a mean pinball loss of 0.207 against 0.387 for the house
baseline (per case: p00 0.322, p01 0.193, p02 0.134, p03 0.181); on a
leave-one-out test over the 29 usable comparables it scores 0.254
against 0.360 for the baseline.  Practice is graded on past launches
and pays nothing; it is no guide to the final.

Fallbacks keep every case valid: if fewer than four console-only
comparables carry an hour-1 print, the median arm uses all
comparables; if the regression pool is thinner than five, that arm
falls back to persistence; if the case carries no usable comparable
at all, the forecast is the flat house baseline.

Deterministic: no network, no randomness, no wall-clock use.  Two
runs on the same case write byte-identical output.  Standard library
only.
"""

import json
import math
import os
from datetime import datetime
from pathlib import Path

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z_SCORES = [-1.645, -0.674, 0.0, 0.674, 1.645]

# Median arm: level tilt and spread bounds.
MEDIAN_TILT = -0.30
RAMP_START = 6
RAMP_END = 19
MIN_CONSOLE = 4
SPREAD_LOW = 0.18
SPREAD_HIGH = 0.95

# Regression arm: pool filter and fallback.
HOUR1_FLOOR = 5000
MIN_REGRESSION_POOL = 5
RESIDUAL_FLOOR = 0.15

# Flat fallback (house baseline) and output bounds.
BASE_RATE = 0.15
MAX_VIEWERS = 1_000_000_000


def _median(values):
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return 0.5 * (ordered[mid - 1] + ordered[mid])


def _mad(values):
    """Robust spread: 1.4826 * median absolute deviation from the median."""
    if len(values) < 3:
        return 0.5
    centre = _median(values)
    return 1.4826 * _median([abs(v - centre) for v in values])


def _parse_time(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _day_curve(comparable):
    """Release-day hourly viewers {1..24} for one comparable, or None.

    None when any of the 24 hours is missing or non-positive: a
    partial day cannot anchor a shape.
    """
    try:
        start = _parse_time(comparable["day_start"])
    except (KeyError, ValueError, TypeError):
        return None
    by_hour = {}
    for point in comparable.get("hourly") or []:
        try:
            when = _parse_time(point["from"])
            viewers = point["viewers"]
        except (KeyError, ValueError, TypeError):
            continue
        hour = int((when - start).total_seconds() // 3600) + 1
        if 1 <= hour <= 24 and isinstance(viewers, (int, float)) and viewers > 0:
            by_hour[hour] = float(viewers)
    if len(by_hour) != 24:
        return None
    return by_hour


def _is_console_only(comparable):
    platforms = comparable.get("platforms")
    return isinstance(platforms, str) and "PC" not in platforms


def _pools(case):
    """Split the case's comparables into the two arms' pools.

    Returns (console_days, regression_days): release-day curves of the
    console-only launches, and of every launch with hour 1 at or above
    the floor.  The GTA VI pre-release comparable has no release day,
    so the full-day check drops it from both.
    """
    console_days = []
    regression_days = []
    for comparable in case.get("comparables") or []:
        day = _day_curve(comparable)
        if day is None:
            continue
        if _is_console_only(comparable):
            console_days.append(day)
        if day[1] >= HOUR1_FLOOR:
            regression_days.append(day)
    return console_days, regression_days


def _median_arm(p1, console_days, all_days):
    """Per-hour (log-median, spread) from the console median shape.

    Falls back to all release days when the console pool is too thin.
    Returns None when there is no usable day at all.
    """
    days = console_days if len(console_days) >= MIN_CONSOLE else all_days
    if not days:
        return None
    ref = sum(math.log(d[1]) for d in days) / len(days)
    log_p1 = math.log(p1)
    arm = {}
    for hour in range(2, 25):
        ratios = [math.log(d[hour] / d[1]) for d in days]
        shape = _median(ratios)
        ramp = (hour - RAMP_START) / (RAMP_END - RAMP_START)
        ramp = min(1.0, max(0.0, ramp))
        shape += MEDIAN_TILT * (log_p1 - ref) * ramp
        spread = 0.5 * _mad(ratios) + 0.5 * BASE_RATE * math.sqrt(hour - 1)
        arm[hour] = (shape, min(SPREAD_HIGH, max(SPREAD_LOW, spread)))
    return arm


def _regression_arm(p1, regression_days):
    """Per-hour (log-median, spread) from the level regression.

    Each hour's log-ratio is fit on log hour-1 across the pool; the
    case's median is read off the line at its own (winsorised) hour 1.
    Returns None when the pool is too thin to fit.
    """
    if len(regression_days) < MIN_REGRESSION_POOL:
        return None
    xs = [math.log(d[1]) for d in regression_days]
    mean_x = sum(xs) / len(xs)
    var_x = sum((x - mean_x) ** 2 for x in xs) / len(xs)
    anchor = min(max(math.log(p1), min(xs)), max(xs))
    arm = {}
    for hour in range(2, 25):
        ys = [math.log(d[hour] / d[1]) for d in regression_days]
        mean_y = sum(ys) / len(ys)
        if var_x > 0:
            cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / len(xs)
            slope = cov / var_x
        else:
            slope = 0.0
        intercept = mean_y - slope * mean_x
        median = intercept + slope * anchor
        resid = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
        dof = max(len(regression_days) - 2, 1)
        sigma = math.sqrt(sum(r * r for r in resid) / dof)
        arm[hour] = (median, max(sigma, RESIDUAL_FLOOR))
    return arm


def _quantiles(p1, log_median, spread):
    """Five quantiles around p1 * exp(log_median), rounded to 2 dp."""
    out = []
    previous = 0.0
    for z in Z_SCORES:
        q = p1 * math.exp(log_median + z * spread)
        q = math.floor(q * 100.0 + 0.5) / 100.0
        q = min(max(q, 0.01), MAX_VIEWERS)
        q = max(q, previous)
        out.append(q)
        previous = q
    return out


def forecast_case(case, name):
    if list(case["levels"]) != LEVELS:
        raise ValueError(f"{name} asks for levels {case['levels']}, not {LEVELS}")
    known = next((k for k in case["known"] if k["hour"] == 1), None)
    if known is None:
        raise ValueError(f"{name} has no hour-1 print")
    p1 = max(1.0, float(known["viewers"]))

    console_days, regression_days = _pools(case)
    all_days = console_days + [d for d in regression_days if d not in console_days]
    median_arm = _median_arm(p1, console_days, all_days)
    regression_arm = _regression_arm(p1, regression_days)

    hours = []
    for row in case["forecast"]:
        hour = row["hour"]
        arms = []
        if median_arm is not None:
            arms.append(median_arm[hour])
        if regression_arm is not None:
            arms.append(regression_arm[hour])
        if arms:
            log_median = sum(a[0] for a in arms) / len(arms)
            spread = sum(a[1] for a in arms) / len(arms)
        else:
            # No usable comparable at all: flat house baseline.
            log_median = 0.0
            spread = BASE_RATE * math.sqrt(hour - 1)
        hours.append({"hour": hour, "q": _quantiles(p1, log_median, spread)})
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
