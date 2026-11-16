"""Compares the three methods on the real faults recorded with the fan fixed
to the board (11 and 12 November): the trained baseline, the adaptive
detector and a fixed limit. Table I of the article.

Each fault was recorded from the fan's start-up, but on a real machine it
appears after a while of healthy operation. So each case appends a healthy
recording and, right after it, the fault without its 5 min of warm-up:
  - unbalance:   night of 12 November + firm tape (up to 16.2 min, before it
                 came loose);
  - loose part:  night of 12 November + flapping tape (11 November);
  - obstruction: hot afternoon of 12 November + block in front (recorded
                 just before it, in the same heat).

Training of the baseline: night, first 200 min, and hot afternoon, first
28 min (the default training). The test starts after that. The fixed limit
alarms when the total vibration exceeds 1.25 times the training median. The
adaptive detector learns by itself, from the end of the warm-up of each
sequence.

For each method:
  - false alarm: fraction of the healthy test windows in alarm;
  - fault: fraction of the fault windows in alarm and the time to a steady
    alarm (more than half of the next minute in alarm), counted from the
    splice;
  - simulated slow fault on the test stretch of the night and of the
    afternoon: how far above normal the vibration was at the steady alarm.

Output: results/method_comparison_real_faults.txt

Usage: .venv/bin/python analysis/evaluation/compare_methods_real_faults.py
"""

import os
import sys
from contextlib import redirect_stdout

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths  # noqa: E402,F401
from adaptive import AdaptiveDetector  # noqa: E402
from csv_format import COLUMNS  # noqa: E402
from trained_baseline import WARMUP_S, TrainedBaseline, read_csv, scale_vibration  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MIN = 60
METHODS = ("trained baseline", "adaptive", "fixed limit")
FIXED_LIMIT = 1.25         # times the median total vibration of training
SLOW_START_S = 4 * 60      # the simulated slow fault starts 4 min into the test


def read(name):
    return read_csv(os.path.join(ROOT, "data", f"{name}.csv"))


def adaptive(df, from_s=0):
    """Alarms of the adaptive detector in each window. With from_s, it only
    starts seeing the recording from there: it switches on with the motor
    already warm."""
    det = AdaptiveDetector()
    since = (df.t - df.t.iloc[0]).to_numpy()
    out = np.zeros(len(df), bool)
    rows = df[COLUMNS[1:]].to_dict("records")
    for k in np.flatnonzero(since >= from_s):
        r = det.add(float(df.t.iloc[k]), rows[k])
        out[k] = bool(r.get("outside"))
    return out


def steady_alarm(t, out, after):
    """First instant after `after` at which more than half of the windows of
    the next minute are in alarm. A lone alarm, which also shows up with no
    fault, does not count as a detection."""
    for k in np.flatnonzero(t >= after):
        minute = (t >= t[k]) & (t < t[k] + 60)
        if out[minute].mean() > 0.5:
            return t[k]
    return None


def splice(healthy, fault, from_s, to_s):
    """The fault, from from_s to to_s since its start, right after the healthy part."""
    since = (fault.t - fault.t.iloc[0]).to_numpy()
    f = fault[(since >= from_s) & (since < to_s)].copy()
    step = 512 / f.rate_hz.iloc[0]
    f["t"] = f.t - f.t.iloc[0] + healthy.t.iloc[-1] + step
    return pd.concat([healthy, f], ignore_index=True), healthy.t.iloc[-1] + step


def alarms(df, baseline, ref, from_s):
    since = (df.t - df.t.iloc[0]).to_numpy()
    sel = since >= from_s
    return df.t.to_numpy()[sel], {
        "trained baseline": baseline.detect(df, from_s=from_s).out.to_numpy(),
        "adaptive": adaptive(df, from_s=WARMUP_S)[sel],
        "fixed limit": (df.rms_total > FIXED_LIMIT * ref).to_numpy()[sel],
    }


def main():
    night, heat = read("board-bench-night"), read("board-bench-hot-afternoon")
    training = [(night, 0, 200 * MIN), (heat, 0, 28 * MIN)]
    baseline = TrainedBaseline().train(training)
    ref = float(np.median(np.concatenate([
        d.rms_total[((d.t - d.t.iloc[0]) >= WARMUP_S) & ((d.t - d.t.iloc[0]) < e)]
        for d, _, e in training])))
    print(f"Training: {baseline.n_train} windows; fixed limit at {FIXED_LIMIT} x {ref:.4f} g\n")

    cases = [
        ("unbalance", night, 200 * MIN, read("board-tape-firm"), 16.2 * MIN),
        ("loose part", night, 200 * MIN, read("board-tape-loose"), np.inf),
        ("obstruction", heat, 28 * MIN, read("board-front-obstructed"), np.inf),
    ]
    print("Healthy + fault sequences")
    for name, healthy, test_s, fault, end in cases:
        df, joint = splice(healthy, fault, WARMUP_S, end)
        t, out = alarms(df, baseline, ref, test_s)
        before, after = t < joint, t >= joint
        print(f"  {name} ({after.sum()} fault windows, {before.sum()} healthy before)")
        for m in METHODS:
            steady = steady_alarm(t, out[m], joint)
            delay = "never" if steady is None else f"{(steady - joint) / MIN:.1f} min"
            print(f"    {m:16s} false alarm before {100 * out[m][before].mean():5.1f}%"
                  f"  fault in alarm {100 * out[m][after].mean():5.1f}%  steady alarm: {delay}")

    print("\nOther healthy recordings (false alarm after warm-up)")
    others = [("session of 11 Nov (board-place6)", read("board-place6"), 0, np.inf),
              ("after the tape flew away", read("board-tape-firm"), 20 * MIN, np.inf)]
    for name, df, start, end in others:
        since = (df.t - df.t.iloc[0]).to_numpy()
        df = df[since < end].reset_index(drop=True)
        t, out = alarms(df, baseline, ref, max(start, WARMUP_S))
        print(f"  {name}: " + "  ".join(f"{m} {100 * out[m].mean():.1f}%" for m in METHODS))

    print("\nSimulated slow fault on the test (the vibration strength rises at the rate per minute,")
    print(f"from {SLOW_START_S // MIN} min into the test): how far above normal at the steady alarm")
    for name, df, test_s in [("night", night, 200 * MIN), ("hot afternoon", heat, 28 * MIN)]:
        since = (df.t - df.t.iloc[0]).to_numpy()
        start = test_s + SLOW_START_S
        for rate in (0.005, 0.01):
            sim = scale_vibration(df, 1.0 + rate * np.maximum(0.0, since - start) / MIN)
            t, out = alarms(sim, baseline, ref, test_s)
            t = t - df.t.iloc[0]
            res = []
            for m in METHODS:
                steady = steady_alarm(t, out[m], start)
                res.append(f"{m} " + ("never" if steady is None else f"+{100 * rate * (steady - start) / MIN:.0f}%"))
            print(f"  {name}, {100 * rate:.1f}%/min: " + "  ".join(res))


if __name__ == "__main__":
    output = os.path.join(ROOT, "results", "method_comparison_real_faults.txt")
    with open(output, "w", encoding="utf-8") as f, redirect_stdout(f):
        main()
    print(open(output, encoding="utf-8").read())
