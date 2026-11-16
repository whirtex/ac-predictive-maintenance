"""Compares the vibration of the fan fixed to the board in five places with
that of the loose fan in the older recordings.

Each row is a place: the dot is the median of the total vibration and the
bar goes from the 5th to the 95th percentile of the windows. In the older
recordings, the first 5 minutes (warm-up) are left out.

Output: results/five_places_board.png

Usage: .venv/bin/python analysis/figures/five_places_figure.py
"""

import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths  # noqa: E402,F401
from csv_format import CLIMATE, COLUMNS, derive_table  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BLUE = "#2a78d6"
GREY = "#8a8984"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"

BOARD = [
    ("board-place1", "wooden bench"),
    ("board-place2", "bedside table"),
    ("board-place3", "bedroom floor"),
    ("board-place4", "bed"),
    ("board-place5", "lacquered wood"),
]
LOOSE = [
    ("loose-wooden-table-night1", "wooden table (night 1)"),
    ("loose-marble-bench-afternoon", "marble bench (afternoon)"),
    ("loose-wooden-table-night2", "wooden table (night 2)"),
]


def read(name, skip_s=0):
    d = pd.read_csv(os.path.join(ROOT, "data", f"{name}.csv"),
                    names=COLUMNS + CLIMATE, comment="#")
    d = derive_table(d)
    if skip_s:
        t = pd.to_datetime(d["datetime"])
        d = d[t >= t.iloc[0] + pd.Timedelta(seconds=skip_s)]
    return d["rms_total"]


def main():
    rows = []
    for name, label in LOOSE:
        rows.append((label, read(name, 300), GREY))
    for name, label in BOARD:
        rows.append((label, read(name), BLUE))

    fig, ax = plt.subplots(figsize=(8, 4.4), dpi=200)
    for i, (label, v, color) in enumerate(reversed(rows)):
        ax.plot([v.quantile(0.05), v.quantile(0.95)], [i, i], color=color, lw=2,
                solid_capstyle="round")
        ax.plot(v.median(), i, "o", ms=8, color=color, mec="white", mew=1.5)
        ax.text(v.quantile(0.95) + 0.004, i, f"{v.median():.3f} g", va="center",
                fontsize=9, color=INK_2)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r for r, _, _ in reversed(rows)], fontsize=10, color=INK)
    ax.axhline(len(BOARD) - 0.5, color=GRID, lw=1)
    ax.text(0.003, len(BOARD) - 0.35, "loose fan (6 and 7 Nov)", color=GREY,
            fontsize=9, weight="bold")
    ax.text(0.003, -0.75, "fan fixed to the board (11 Nov)", color=BLUE,
            fontsize=9, weight="bold")
    ax.set_ylim(-1, len(rows) - 0.3)
    ax.set_xlim(0, None)
    ax.set_xlabel("total vibration (g): dot = median, bar = 90% of the windows",
                  fontsize=9, color=INK_2)
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.set_title("Fixed to a board, the normal barely changes with the place",
                 fontsize=12, color=INK, loc="left", weight="bold")
    fig.tight_layout()
    output = os.path.join(ROOT, "results", "five_places_board.png")
    fig.savefig(output, facecolor="white")
    print(output)


if __name__ == "__main__":
    main()
