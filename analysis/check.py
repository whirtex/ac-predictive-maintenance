"""Runs a recording through the trained model and says where it saw something out of the normal.

Shows a chart: the vibration on top, the alarm moments below.
"""
import pickle
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from trained_baseline import read_csv

ROOT = Path(__file__).resolve().parent.parent


def main():
    path = ROOT / "model.pkl"
    if not path.exists():
        print("There is no model yet. Run train.bat (Windows) or ./train (Mac) first.")
        return
    with open(path, "rb") as f:
        model = pickle.load(f)
    files = sorted((ROOT / "data").glob("*.csv"), key=lambda f: f.stat().st_mtime)
    print("Recordings in the data folder (the last one is the newest):")
    for k, f in enumerate(files, 1):
        print(f"  {k}. {f.stem}")
    answer = input("Which one to check? Number, or Enter for the newest: ").strip()
    chosen = files[-1] if not answer else files[int(answer) - 1]

    df = read_csv(chosen)
    r = model.detect(df)
    valid = ~r.warming
    mins = (r.t - r.t.iloc[0]).to_numpy() / 60
    print(f"\n{chosen.stem}: {mins[-1]:.0f} min")
    print("  The first 5 minutes are the motor warming up: no alarm.")
    print(f"  Out of the normal {100 * r.out[valid].mean():.1f}% of the time.")
    if r.new_climate[valid].mean() > 0.2:
        print("  Note: the climate of this recording differs from training. Record a few")
        print("  healthy minutes here, add them to training and train again.")
    if r.out.any():
        print(f"  Measure that weighed most: {r.measure[r.out].mode().iat[0]}")

    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(10, 5), sharex=True,
                                  gridspec_kw={"height_ratios": [3, 1]})
    ax.plot(mins, df.rms_total.to_numpy(), ".", ms=2, alpha=0.3)
    ax.set_ylabel("total vibration (g)")
    ax.set_title(chosen.stem, loc="left")
    ax2.plot(mins[r.out], np.zeros(r.out.sum()), "|", color="red", ms=12)
    ax2.axvspan(0, model.warmup_s / 60, color="#ddd")
    ax2.set_yticks([])
    ax2.set_xlabel("minutes  (grey: warming up; red: out of the normal)")
    fig.tight_layout()
    plt.show()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("Error:", error)
        sys.exit(1)
