"""Desenha o diagrama da arquitetura do prototipo para o artigo.

Saida: assets/arquitetura.png, em ingles como o artigo.

Uso (na pasta predictive-maintenance):
    .venv/bin/python analysis/figura_arquitetura.py
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

PASTA = Path(__file__).resolve().parent.parent
TINTA = "#0b0b0b"
TINTA_2 = "#52514e"
BORDA = "#9a9892"
FUNDO_BORDA = "#f1f0ec"
FUNDO_PC = "#eaf2fb"

BLOCOS = [
    # (x, titulo, linhas, fundo)
    (0.0, "Sensors", ["ADXL345 accelerometer", "(I2C, 400 Hz FIFO)",
                      "INA219 current monitor", "(I2C)", "Fan tachometer",
                      "(interrupt)"], FUNDO_BORDA),
    (2.35, "ESP32 (edge)", ["512-sample windows", "per axis: RMS, peak,",
                            "kurtosis, FFT peak", "and its frequency",
                            "mean current, speed"], FUNDO_BORDA),
    (4.7, "Link", ["USB serial", "(prototype)", "", "MQTT", "(field installation)"],
     "#ffffff"),
    (7.05, "Detector", ["5 orientation-free totals", "Isolation Forest",
                        "+ robust ruler", "adaptive baseline",
                        "installation reference"], FUNDO_PC),
    (9.4, "Panel", ["alarm naming the", "measurement that", "deviated",
                    "drift vs. installation", "investigation request"], FUNDO_PC),
]
LARGURA = 2.0
ALTURA = 2.3


def main():
    plt.rcParams.update({"font.family": "DejaVu Sans"})
    fig, ax = plt.subplots(figsize=(7.2, 1.9))
    ax.set_xlim(-0.05, 11.45)
    ax.set_ylim(-0.35, ALTURA + 0.05)
    ax.axis("off")
    for x, titulo, linhas, fundo in BLOCOS:
        ax.add_patch(FancyBboxPatch((x, 0), LARGURA, ALTURA,
                                    boxstyle="round,pad=0,rounding_size=0.12",
                                    facecolor=fundo, edgecolor=BORDA, linewidth=0.9))
        ax.text(x + LARGURA / 2, ALTURA - 0.28, titulo, ha="center", va="center",
                fontsize=8.5, fontweight="bold", color=TINTA)
        for i, linha in enumerate(linhas):
            ax.text(x + LARGURA / 2, ALTURA - 0.62 - 0.29 * i, linha, ha="center",
                    va="center", fontsize=6.4, color=TINTA_2)
    for x, _, _, _ in BLOCOS[:-1]:
        ax.add_patch(FancyArrowPatch((x + LARGURA + 0.04, ALTURA / 2),
                                     (x + 2.35 - 0.04, ALTURA / 2),
                                     arrowstyle="-|>", mutation_scale=9,
                                     color=TINTA_2, linewidth=1))
    ax.text(0.0 + (2.35 + LARGURA) / 2, -0.2, "at the equipment", ha="center",
            fontsize=6.6, color=TINTA_2, style="italic")
    ax.text(7.05 + (2.35 + LARGURA) / 2, -0.2, "remote application (laptop in the prototype)",
            ha="center", fontsize=6.6, color=TINTA_2, style="italic")
    fig.tight_layout(pad=0.1)
    destino = PASTA / "assets" / "arquitetura.png"
    fig.savefig(destino, dpi=300)
    plt.close(fig)
    print(destino.relative_to(PASTA))


if __name__ == "__main__":
    main()
