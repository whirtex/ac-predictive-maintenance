"""Desenha o diagrama da arquitetura do prototipo para o artigo.

Saida: assets/arquitetura.png, em ingles como o artigo, na largura de uma
coluna do SBrT.

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
    (0.0, "Sensors", ["ADXL345", "INA219", "tachometer"], FUNDO_BORDA),
    (2.35, "ESP32", ["features per", "1.23 s window"], FUNDO_BORDA),
    (4.7, "Link", ["USB (bench)", "MQTT (field)"], "#ffffff"),
    (7.05, "Detector", ["forest + ruler", "two baselines"], FUNDO_PC),
    (9.4, "Panel", ["alarm naming", "the measure,", "drift"], FUNDO_PC),
]
LARGURA = 2.0
ALTURA = 2.3


def main():
    plt.rcParams.update({"font.family": "DejaVu Sans"})
    fig, ax = plt.subplots(figsize=(3.45, 1.05))
    ax.set_xlim(-0.05, 11.45)
    ax.set_ylim(-0.5, ALTURA + 0.05)
    ax.axis("off")
    for x, titulo, linhas, fundo in BLOCOS:
        ax.add_patch(FancyBboxPatch((x, 0), LARGURA, ALTURA,
                                    boxstyle="round,pad=0,rounding_size=0.12",
                                    facecolor=fundo, edgecolor=BORDA, linewidth=0.9))
        ax.text(x + LARGURA / 2, ALTURA - 0.4, titulo, ha="center", va="center",
                fontsize=6.6, fontweight="bold", color=TINTA)
        for i, linha in enumerate(linhas):
            ax.text(x + LARGURA / 2, ALTURA - 1.0 - 0.45 * i, linha, ha="center",
                    va="center", fontsize=5.4, color=TINTA_2)
    for x, _, _, _ in BLOCOS[:-1]:
        ax.add_patch(FancyArrowPatch((x + LARGURA + 0.04, ALTURA / 2),
                                     (x + 2.35 - 0.04, ALTURA / 2),
                                     arrowstyle="-|>", mutation_scale=6,
                                     color=TINTA_2, linewidth=1))
    ax.text(0.0 + (2.35 + LARGURA) / 2, -0.3, "at the equipment", ha="center",
            fontsize=5.4, color=TINTA_2, style="italic")
    ax.text(7.05 + (2.35 + LARGURA) / 2, -0.3, "remote (laptop)",
            ha="center", fontsize=5.4, color=TINTA_2, style="italic")
    fig.tight_layout(pad=0.1)
    destino = PASTA / "assets" / "arquitetura.png"
    fig.savefig(destino, dpi=300)
    plt.close(fig)
    print(destino.relative_to(PASTA))


if __name__ == "__main__":
    main()
