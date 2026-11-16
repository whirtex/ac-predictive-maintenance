"""Evaluates the two-baseline detector on the three recorded sessions.

The sessions (data/rep1.csv to rep3.csv) are the fan in normal operation.
The faults are simulated in software over them, and the report says so. It
measures:

  1. false alarms on normal data, after the initial learning;
  2. a simulated sudden fault (+30% in vibration, in the peak and in the
     strength of the dominant frequency, for 60 s), injected at several
     moments of each session: the fraction of fault windows that became an
     alarm, and what fired it (only the ruler, only the model, both);
  3. a simulated slow change (1%, 1.5% and 2% per minute): the fraction of
     windows in alarm during the rise and the "vs. start" value at the end;
  4. the same thing with a frozen baseline, learned once and never updated,
     to measure what adaptation changes.

Outputs in results/ap1/: two_baseline_evaluation.txt and slow_drift_evaluation.png.

Usage (in the repository root):
    .venv/bin/python analysis/ap1/evaluate_two_baselines.py
"""

import csv
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402
import numpy as np  # noqa: E402

import os  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths  # noqa: E402,F401
from adaptive import AdaptiveDetector  # noqa: E402
from csv_format import COLUMNS, valid_line  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LEARNING_S = 120
FAULT_S = 60
FAULT_FACTOR = 1.30
NEVER = 10 ** 9     # update_s of the frozen baseline: it never relearns


def load_session(r):
    windows = []
    t = 0.0
    with open(ROOT / "data" / f"rep{r}.csv", encoding="utf-8") as f:
        for line in csv.reader(f):
            if not line or line[0].startswith("#") or not valid_line(line):
                continue
            if line[0] == "datetime":
                continue
            w = dict(zip(COLUMNS, line))
            try:
                t += 512 / float(w["rate_hz"])
            except ValueError:
                continue
            windows.append((t, w))
    return windows


def scale(w, factor):
    w = dict(w)
    for a in "xyz":
        for k in ("rms", "peak", "domamp"):
            w[f"{a}_{k}"] = float(w[f"{a}_{k}"]) * factor
    return w


def run(windows, factor=lambda t: 1.0, update_s=None):
    det = AdaptiveDetector() if update_s is None else AdaptiveDetector(update_s=update_s)
    out = []
    for t, w in windows:
        f = factor(t)
        r = det.add(t, scale(w, f) if f != 1.0 else w)
        reason = r.get("reason") or ""
        out.append({
            "t": t, "phase": r["phase"], "outside": bool(r.get("outside")),
            "ruler": "ruler" in reason, "model": "model" in reason,
            "vib": r["measures"]["rms_total"], "base": r.get("rms_mean", np.nan),
            "drift": r.get("drift", np.nan), "investigate": bool(r.get("investigate")),
        })
    return out, det


def pct(x):
    return f"{100 * x:5.1f}%"


def main():
    sessions = {r: load_session(r) for r in (1, 2, 3)}

    print("TWO-BASELINE DETECTOR: evaluation on the three recorded sessions")
    print("Faults simulated in software over real normal recordings.\n")

    # --- 1 and 4. false alarms: adaptive and frozen baseline --------------
    print("== 1. FALSE ALARMS ON NORMAL DATA (after the 2 min of learning)")
    total = {"adaptive": [0, 0], "frozen": [0, 0]}
    for r, win in sessions.items():
        line = f"  session {r} ({win[-1][0] / 60:4.1f} min):"
        for name, current in (("adaptive", None), ("frozen", NEVER)):
            res, _ = run(win, update_s=current)
            det = [x for x in res if x["phase"] == "detecting"]
            fa = sum(x["outside"] for x in det)
            total[name][0] += fa
            total[name][1] += len(det)
            line += f"   {name} baseline: {pct(fa / len(det))} ({fa} of {len(det)})"
        print(line)
    for name, (fa, n) in total.items():
        print(f"  total, {name} baseline: {pct(fa / n)} ({fa} of {n} windows)")

    # --- 2. simulated sudden fault -----------------------------------------
    print("\n== 2. SIMULATED SUDDEN FAULT (+30% for 60 s, every 5 min of each session)")
    count = {"alarm": 0, "ruler": 0, "model": 0, "both": 0, "windows": 0, "injections": 0,
             "detected": 0, "investigate": 0}
    for r, win in sessions.items():
        end = win[-1][0]
        for start in np.arange(300, end - 2 * FAULT_S, 300):
            res, _ = run(win, lambda t, i=start: FAULT_FACTOR if i <= t < i + FAULT_S else 1.0)
            inside = [x for x in res if start <= x["t"] < start + FAULT_S]
            count["injections"] += 1
            count["detected"] += any(x["outside"] for x in inside)
            count["windows"] += len(inside)
            count["alarm"] += sum(x["outside"] for x in inside)
            count["ruler"] += sum(x["ruler"] and not x["model"] for x in inside)
            count["model"] += sum(x["model"] and not x["ruler"] for x in inside)
            count["both"] += sum(x["ruler"] and x["model"] for x in inside)
            count["investigate"] += any(x["investigate"] for x in res)
    n = count["windows"]
    print(f"  {count['injections']} faults injected, {count['detected']} detected")
    print(f"  fault windows in alarm: {pct(count['alarm'] / n)} ({count['alarm']} of {n})")
    print(f"    ruler only:  {pct(count['ruler'] / n)}")
    print(f"    model only:  {pct(count['model'] / n)}")
    print(f"    both:        {pct(count['both'] / n)}")
    print(f"  inspection requests (persistent change): {count['investigate']}")

    # --- 3. simulated slow change ------------------------------------------
    # starts at minute 10 of session 3, after the natural drop at the start
    print("\n== 3. SIMULATED SLOW CHANGE (session 3, from minute 10;"
          " the rise starts 4 min later)")
    base_win = [(t - 600, w) for t, w in sessions[3] if t >= 600]
    curves = {}
    for rate in (0.010, 0.015, 0.020):
        res, _ = run(base_win, lambda t, k=rate: 1.0 + k * max(0.0, t - 240) / 60)
        rise = [x for x in res if x["t"] >= 240 and x["phase"] == "detecting"]
        drifts = [x["drift"] for x in res if not np.isnan(x["drift"])]
        curves[rate] = res
        print(f"  {100 * rate:.1f}% per minute: alarm in {pct(np.mean([x['outside'] for x in rise]))}"
              f" of the rise windows; vs. start at the end: {drifts[-1]:+.1f}%")
        requested = [x["t"] for x in res if x["investigate"]]
        print("      investigate: " + (f"requested {(requested[0] - 240) / 60:.1f} min after the"
                                       " rise starts" if requested else "never"))
        res_frozen, _ = run(base_win, lambda t, k=rate: 1.0 + k * max(0.0, t - 240) / 60,
                            update_s=NEVER)
        rise_frozen = [x for x in res_frozen if x["t"] >= 240 and x["phase"] == "detecting"]
        print(f"      with frozen baseline: alarm in {pct(np.mean([x['outside'] for x in rise_frozen]))}"
              " of the rise windows")

    # --- figure: slow change at 1.5% per minute ------------------------------
    res = curves[0.015]
    t = np.array([x["t"] for x in res]) / 60
    vib = np.array([x["vib"] for x in res])
    base = np.array([x["base"] for x in res])
    outside = np.array([x["outside"] for x in res])
    det = AdaptiveDetector()
    for tt, w in base_win:
        det.add(tt, w)
        if det.reference:
            break
    ref = det.reference
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
    fig, ax = plt.subplots(figsize=(6.4, 2.8))
    ax.plot(t, vib, color="#2a78d6", linewidth=1, label="vibration")
    ax.plot(t, base, color="#52514e", linewidth=1.6, label="adaptive baseline")
    ax.axhline(ref, color="#1baf7a", linewidth=1.4, linestyle="--", label="installation reference")
    ax.plot(t[outside], vib[outside], "o", color="#d03b3b", markersize=2.5, label="alarm")
    ax.set_xlabel("time (min)")
    ax.set_ylabel("total RMS (g)")
    ax.grid(True, color="#e4e3df", linewidth=0.6)
    ax.legend(frameon=False, ncol=4, loc="lower left", bbox_to_anchor=(0, 1.0), fontsize=8)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    fig.tight_layout()
    fig.savefig(ROOT / "results" / "ap1" / "slow_drift_evaluation.png", dpi=200)
    plt.close(fig)
    print("\nfigure: results/ap1/slow_drift_evaluation.png (1.5% per minute)")


if __name__ == "__main__":
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        main()
    text = buffer.getvalue()
    (ROOT / "results" / "ap1").mkdir(parents=True, exist_ok=True)
    (ROOT / "results" / "ap1" / "two_baseline_evaluation.txt").write_text(text, encoding="utf-8")
    sys.stdout.write(text)
