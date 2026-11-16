"""Draws the prototype architecture diagram for the article.

Output: assets/architecture.png, in English like the article, at the width of
one SBrT column.

Usage (in the repository root):
    .venv/bin/python analysis/figures/architecture_figure.py
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
INK = "#0b0b0b"
INK_2 = "#52514e"
BORDER = "#9a9892"
BG_EDGE = "#f1f0ec"
BG_PC = "#eaf2fb"

BLOCKS = [
    # (x, title, lines, background)
    (0.0, "Sensors", ["ADXL345", "INA219", "tachometer"], BG_EDGE),
    (2.35, "ESP32", ["features per", "1.23 s window"], BG_EDGE),
    (4.7, "Link", ["USB (bench)", "MQTT (field)"], "#ffffff"),
    (7.05, "Detector", ["forest + ruler", "two baselines"], BG_PC),
    (9.4, "Panel", ["alarm naming", "the measure,", "drift"], BG_PC),
]
WIDTH = 2.0
HEIGHT = 2.3


def main():
    plt.rcParams.update({"font.family": "DejaVu Sans"})
    fig, ax = plt.subplots(figsize=(3.45, 1.05))
    ax.set_xlim(-0.05, 11.45)
    ax.set_ylim(-0.5, HEIGHT + 0.05)
    ax.axis("off")
    for x, title, lines, background in BLOCKS:
        ax.add_patch(FancyBboxPatch((x, 0), WIDTH, HEIGHT,
                                    boxstyle="round,pad=0,rounding_size=0.12",
                                    facecolor=background, edgecolor=BORDER, linewidth=0.9))
        ax.text(x + WIDTH / 2, HEIGHT - 0.4, title, ha="center", va="center",
                fontsize=6.6, fontweight="bold", color=INK)
        for i, line in enumerate(lines):
            ax.text(x + WIDTH / 2, HEIGHT - 1.0 - 0.45 * i, line, ha="center",
                    va="center", fontsize=5.4, color=INK_2)
    for x, _, _, _ in BLOCKS[:-1]:
        ax.add_patch(FancyArrowPatch((x + WIDTH + 0.04, HEIGHT / 2),
                                     (x + 2.35 - 0.04, HEIGHT / 2),
                                     arrowstyle="-|>", mutation_scale=6,
                                     color=INK_2, linewidth=1))
    ax.text(0.0 + (2.35 + WIDTH) / 2, -0.3, "at the equipment", ha="center",
            fontsize=5.4, color=INK_2, style="italic")
    ax.text(7.05 + (2.35 + WIDTH) / 2, -0.3, "remote (laptop)",
            ha="center", fontsize=5.4, color=INK_2, style="italic")
    fig.tight_layout(pad=0.1)
    target = ROOT / "assets" / "architecture.png"
    fig.savefig(target, dpi=300)
    plt.close(fig)
    print(target.relative_to(ROOT))


if __name__ == "__main__":
    main()
