"""Figure of the three real faults for the article, at the width of both
columns: the total vibration (left) and the dominant frequency (right) of
healthy operation and of the three faults, with the fan fixed to the board,
on the same bench.

Output: results/real_faults.png

Usage: .venv/bin/python analysis/figures/real_faults_figure.py
"""

import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths  # noqa: E402,F401
from trained_baseline import read_csv  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INK_2 = "#52514e"
GRID = "#e4e3df"

# file, label, color, up to which minute, style
SERIES = [
    ("board-bench-night", "healthy, night (26 °C)", "#6f6e69", 22, "-"),
    ("board-bench-hot-afternoon", "healthy, afternoon (30 °C)", "#b5b3ad", 22, "-"),
    ("board-tape-firm", "unbalance: tape firmly on a blade", "#2a78d6", 16.2, "-"),
    ("board-tape-loose", "loose part: tape flapping on a blade", "#e07b00", 22, "-"),
    ("board-front-obstructed", "obstruction: block 2–5 cm from the outlet", "#2e9e5b", 22, "-"),
]


def main():
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 7})
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.1, 2.2), dpi=300)
    for name, label, color, until, style in SERIES:
        d = read_csv(os.path.join(ROOT, "data", f"{name}.csv"))
        m = (d.t - d.t.iloc[0]) / 60
        d, m = d[m < until], m[m < until]
        smooth = d.rms_total.rolling(45, center=True, min_periods=20).median()
        a1.plot(m, d.rms_total, color=color, lw=0.4, alpha=0.25)
        a1.plot(m, smooth, color=color, lw=1.4, ls=style, label=label)
        a2.plot(m, d.domfreq, ".", color=color, ms=1.2)
    for ax in (a1, a2):
        ax.axvspan(0, 5, color=GRID, alpha=0.6, lw=0)
        ax.grid(color=GRID, lw=0.6)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.tick_params(colors=INK_2, labelsize=6.5)
        ax.set_xlabel("minutes since start (shaded: warm-up)", fontsize=6.5, color=INK_2)
        ax.set_xlim(0, 22.5)
    a1.set_ylim(0.03, 0.125)
    a1.set_ylabel("total vibration (g)", fontsize=6.5, color=INK_2)
    a2.set_ylim(0, 105)
    a2.set_yticks([0, 15, 46, 93])
    a2.set_ylabel("dominant frequency (Hz)", fontsize=6.5, color=INK_2)
    fig.legend(*a1.get_legend_handles_labels(), loc="upper center", ncol=3,
               fontsize=6, frameon=False, handlelength=1.6, columnspacing=1.2)
    fig.tight_layout(rect=(0, 0, 1, 0.84), w_pad=1.5)
    output = os.path.join(ROOT, "results", "real_faults.png")
    fig.savefig(output, facecolor="white")
    print(output)


if __name__ == "__main__":
    main()
