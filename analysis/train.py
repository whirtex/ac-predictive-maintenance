"""Trains the model on the healthy recordings of the data folder and saves it to model.pkl.

Only recordings of the fan working WELL go in. The first 5 minutes of each
one (motor warming up) are left out automatically."""
import pickle
import sys
from pathlib import Path

import numpy as np

from trained_baseline import TrainedBaseline, read_csv

ROOT = Path(__file__).resolve().parent.parent
MIN = 60
# good stretches of known recordings, in minutes since the start
STRETCHES = {}


def main():
    files = sorted((ROOT / "data").glob("*.csv"))
    if not files:
        print("No recording in the data folder.")
        return
    print("Recordings in the data folder:")
    for k, f in enumerate(files, 1):
        print(f"  {k}. {f.stem}")
    answer = input("Which go into training? Numbers separated by spaces, or Enter for all: ").strip()
    chosen = files if not answer else [files[int(x) - 1] for x in answer.split()]

    training = []
    for f in chosen:
        df = read_csv(f)
        minutes = (df.t.iloc[-1] - df.t.iloc[0]) / MIN
        for start, end in STRETCHES.get(f.stem, [(0, np.inf)]):
            training.append((df, start * MIN, end * MIN))
        print(f"  {f.stem}: {minutes:.0f} min")
    model = TrainedBaseline().train(training)
    with open(ROOT / "model.pkl", "wb") as out:
        pickle.dump(model, out)
    (t0, h0), (t1, h1) = model.climate_range
    print(f"\nModel trained on {model.n_train} windows.")
    print(f"Climate it knows: {t0:.1f} to {t1:.1f} C, {h0:.0f} to {h1:.0f}% humidity.")
    print("Saved to model.pkl. Now use check.bat (Windows) or ./check (Mac).")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("Error:", error)
        sys.exit(1)
