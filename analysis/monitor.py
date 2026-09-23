"""Monitor simples da placa: a vibracao num grafico e a corrente no canto.

Nao compara nada, nao tem linha padrao nem avisos. So mostra o que o
aquisicao_esp32 esta medindo agora. Use pelo atalho ./grafico.

Com --seguir, em vez de ler a placa, acompanha o arquivo que o ./gravar
esta gravando. E assim que o ./gravar mostra o grafico.

A placa so pode ser lida por um programa de cada vez: feche o monitor
serial do Arduino IDE e nao rode junto com o ./gravar, que ja abre o
proprio grafico.
"""

import glob
import math
import sys
import threading
import time
from collections import deque

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.ticker import FuncFormatter

from formato import COLUNAS

JANELA_S = 120

SUPERFICIE = "#fcfcfb"
TINTA = "#0b0b0b"
TINTA_2 = "#52514e"
GRADE = "#e4e3df"
SERIE = "#2a78d6"

dados = deque()          # (t, vibracao, corrente)
trava = threading.Lock()


def num(v, casas):
    return f"{v:.{casas}f}".replace(".", ",")


def achar_porta():
    portas = sorted(glob.glob("/dev/cu.usbserial*") + glob.glob("/dev/cu.SLAB*")
                    + glob.glob("/dev/cu.wchusbserial*"))
    if not portas:
        print("A placa não foi encontrada. Confira o cabo USB.")
        sys.exit(1)
    return portas[0]


def interpretar(linha):
    """Devolve (vibracao, corrente) de uma linha do aquisicao_esp32."""
    campos = linha.split(",")
    if len(campos) != len(COLUNAS) or campos[0] == "data_hora":
        return None
    valores = dict(zip(COLUNAS, campos))
    try:
        vibracao = math.sqrt(sum(float(valores[e + "_rms"]) ** 2 for e in "xyz"))
        corrente = float(valores["corrente_ma"]) if valores["corrente_ma"] else None
    except ValueError:
        return None
    return vibracao, corrente


def ler_placa(caminho):
    import serial
    porta = serial.Serial(caminho, 115200, timeout=1)
    porta.readline()   # a primeira linha pode chegar cortada
    while True:
        linha = porta.readline().decode(errors="replace").strip()
        leitura = interpretar(linha)
        if leitura:
            adicionar(time.monotonic(), *leitura)


def seguir(caminho):
    """Acompanha um CSV em gravacao: o que ja existe entra de uma vez, com o
    tempo reconstruido pela duracao das janelas, e o resto entra ao vivo."""
    import os
    while not os.path.exists(caminho):
        time.sleep(0.5)
    with open(caminho, encoding="utf-8") as f:
        antigas = [l.strip() for l in f.read().splitlines()]
        leituras = [r for r in map(interpretar, antigas) if r]
        agora = time.monotonic()
        for i, leitura in enumerate(leituras):
            adicionar(agora - (len(leituras) - 1 - i) * 1.23, *leitura)
        pedaco = ""
        while True:
            novo = f.readline()
            if not novo:
                time.sleep(0.2)
                continue
            pedaco += novo
            if not pedaco.endswith("\n"):
                continue
            leitura = interpretar(pedaco.strip())
            pedaco = ""
            if leitura:
                adicionar(time.monotonic(), *leitura)


def adicionar(t, vibracao, corrente):
    with trava:
        dados.append((t, vibracao, corrente))
        while dados and dados[0][0] < t - JANELA_S:
            dados.popleft()


def montar_janela(relogio=time.monotonic):
    plt.rcParams.update({
        "figure.facecolor": SUPERFICIE, "axes.facecolor": SUPERFICIE,
        "axes.edgecolor": GRADE, "axes.labelcolor": TINTA_2,
        "xtick.color": TINTA_2, "ytick.color": TINTA_2, "font.size": 11,
        "axes.spines.top": False, "axes.spines.right": False,
    })
    fig, ax = plt.subplots(figsize=(10, 5.5))
    try:
        fig.canvas.manager.set_window_title("Vibração e corrente")
    except AttributeError:
        pass
    fig.subplots_adjust(top=0.78)
    virgula = FuncFormatter(lambda v, _: f"{v:g}".replace(".", ","))
    ax.xaxis.set_major_formatter(virgula)
    ax.yaxis.set_major_formatter(virgula)
    ax.grid(True, color=GRADE, linewidth=0.8)
    ax.set_xlim(-JANELA_S, 0)
    ax.set_xlabel("segundos atrás")
    ax.set_ylabel("vibração total (g)")
    linha, = ax.plot([], [], color=SERIE, linewidth=2)

    vib_txt = fig.text(0.125, 0.9, "", fontsize=22, fontweight="bold", color=TINTA)
    vib_rot = fig.text(0.125, 0.85, "vibração agora", fontsize=11, color=TINTA_2)
    cor_txt = fig.text(0.9, 0.9, "", fontsize=22, fontweight="bold", color=TINTA, ha="right")
    cor_rot = fig.text(0.9, 0.85, "corrente agora", fontsize=11, color=TINTA_2, ha="right")
    _ = (vib_rot, cor_rot)

    def atualizar(_):
        agora = relogio()
        with trava:
            copia = list(dados)
        if not copia:
            vib_txt.set_text("aguardando a placa...")
            cor_txt.set_text("")
            return []
        ts = [d[0] - agora for d in copia]
        vs = [d[1] for d in copia]
        linha.set_data(ts, vs)
        ax.set_ylim(0, max(vs) * 1.3)
        _, vibracao, corrente = copia[-1]
        vib_txt.set_text(f"{num(vibracao, 3)} g")
        cor_txt.set_text(f"{num(corrente, 0)} mA" if corrente is not None else "sem INA219")
        return []

    return fig, atualizar


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--seguir":
        threading.Thread(target=seguir, args=(sys.argv[2],), daemon=True).start()
    else:
        porta = achar_porta()
        threading.Thread(target=ler_placa, args=(porta,), daemon=True).start()
    fig, atualizar = montar_janela()
    _animacao = FuncAnimation(fig, atualizar, interval=200, cache_frame_data=False)  # noqa: F841
    try:
        plt.show()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
