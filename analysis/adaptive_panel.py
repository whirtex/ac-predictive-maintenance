"""Painel completo do detector adaptativo. E o que o ./apresentar abre.

Liga a placa num lugar qualquer: nos primeiros 2 minutos o detector
aprende o normal dali, e depois vigia, reaprendendo a cada minuto. O
painel mostra tudo o que ele faz:

  - no alto, o estado (aprendendo, normal, pico, anomalia continua) e um
    quadro com tempo ligado, atualizacoes, alarmes, corrente, rotacao e
    quanto o normal ja mudou desde a instalacao (deriva);
  - no grafico de cima, a vibracao total e a faixa do normal, que mudam
    a cada atualizacao, marcada por uma linha vertical;
  - um ponto vermelho para cada leitura em alerta, seja pelo Isolation
    Forest ou pela protecao contra mudancas fortes; a tecla M mostra a
    nota do modelo num grafico a mais;
  - embaixo, o registro de cada atualizacao e de cada alarme.

Uso:
    python analysis/painel_adaptativo.py                    # placa ao vivo
    python analysis/painel_adaptativo.py --reproduzir data/rep3.csv
    python analysis/painel_adaptativo.py --reproduzir data/rep3.csv --falha 300
        # injeta 60 s de vibracao 30% mais forte aos 300 s da gravacao,
        # para ensaiar; o painel avisa que a falha e simulada

Teclas, com a janela do painel selecionada:
    M   mostra ou esconde o grafico da nota do modelo (Isolation Forest).
    q   fecha

Ctrl+C no terminal, ou fechar a janela, encerra.
"""

import argparse
import glob
import sys
import threading
import time
from collections import deque
from datetime import datetime

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.ticker import FuncFormatter

import adaptive as A
from csv_format import COLUNAS

JANELA_S = 180          # quanto do passado os graficos mostram
SUSTENTADO_S = 2.0      # fora do normal por mais que isso: anomalia continua
PERSISTENTE_S = 60      # mostra aviso antes da escalada de 3 minutos
FIM_EPISODIO_S = 3.0    # de volta ao normal por isso: o episodio acabou
N_AMOSTRAS = 512

SUPERFICIE = "#fcfcfb"
TINTA = "#0b0b0b"
TINTA_2 = "#52514e"
TINTA_3 = "#8a8984"
GRADE = "#e4e3df"
FAIXA = "#e9e8e3"
SERIE = "#2a78d6"
ANOMALIA = "#4a3aa7"
BOM = "#0ca30c"
SERIO = "#ec835a"
CRITICO = "#d03b3b"
NEUTRO = "#8a8984"


def num(v, casas=3):
    return f"{v:.{casas}f}".replace(".", ",")


def duracao(s):
    m, s = divmod(int(s), 60)
    return f"{m} min {s:02d} s" if m else f"{s} s"


class Painel:
    def __init__(self):
        self.detector = A.DetectorAdaptativo()
        self.trava = threading.Lock()
        self.pontos = deque()        # (t, vibracao, anomalia, fora, passou_limite)
        self.mostrar_modelo = False  # tecla M: grafico da nota do modelo
        self.eventos = deque(maxlen=8)
        self.ultimo = None           # resultado da ultima janela
        self.corrente = None
        self.rotacao = None
        self.simulando = False
        self.episodio = None
        self.alarmes = 0
        self.agora = None
        self.atualizacoes_vistas = 0
        self.conexao = None          # aviso de conexao, se a placa caiu

    def hora(self, janela):
        texto = janela.get("data_hora", "")
        if texto and not texto.startswith("boot"):
            return texto[-8:]
        return datetime.now().strftime("%H:%M:%S")

    def adicionar(self, t, janela, simulada=False):
        with self.trava:
            self.agora = t
            self.simulando = simulada
            r = self.detector.adicionar(t, janela)
            self.ultimo = r
            v = r["medidas"]["rms_total"]
            passou = r.get("anomalia") is not None and r["anomalia"] > r["limite"]
            self.pontos.append((t, v, r.get("anomalia"), r.get("fora"), passou))
            while self.pontos and self.pontos[0][0] < t - JANELA_S:
                self.pontos.popleft()
            corrente = janela.get("corrente_ma")
            self.corrente = corrente if corrente == corrente else None
            self.rotacao = r["medidas"]["fdom"] * 60

            hora = self.hora(janela)
            novas = self.detector.atualizacoes[self.atualizacoes_vistas:]
            for a in novas:
                if a["mudanca"] is None:
                    texto = (f"{hora}   ● Aprendeu o normal deste lugar: vibração "
                             f"{num(a['rms_media'])} g, com {a['janelas']} medições")
                else:
                    texto = (f"{hora}   ↻ Atualizou o normal: {num(a['rms_media'])} g "
                             f"({a['mudanca']:+.1f}%), com {a['janelas']} medições").replace(".", ",", 1)
                self.eventos.appendleft(texto)
            self.atualizacoes_vistas = len(self.detector.atualizacoes)

            if r.get("nova_escalada"):
                self.eventos.appendleft(
                    f"{hora}   ■ Anomalia persistente por 3 min: chamar manutenção")
            if r["fase"] == "detectando":
                self._episodio(t, r, hora)

    def _episodio(self, t, r, hora):
        if r["fora"]:
            if self.episodio is None:
                self.episodio = {"inicio": t, "fim": t, "pior": r, "hora": hora}
                self.alarmes += 1
            ep = self.episodio
            ep["fim"] = t
            if r["anomalia"] > ep["pior"]["anomalia"]:
                ep["pior"] = r
        elif self.episodio and t - self.episodio["fim"] >= FIM_EPISODIO_S:
            ep = self.episodio
            dur = ep["fim"] - ep["inicio"] + N_AMOSTRAS / 400
            if dur > SUSTENTADO_S:
                texto = f"■ Anomalia contínua por {duracao(dur)}"
            else:
                texto = "▲ Pico"
            self.eventos.appendleft(f"{ep['hora']}   {texto}: {ep['pior']['detalhe']}")
            self.episodio = None

    def persistente(self):
        """Mais da metade do ultimo minuto em alarme, mesmo picotado."""
        if self.agora is None or self.detector.modelo is None:
            return False
        recentes = [p[3] for p in self.pontos if p[0] >= self.agora - PERSISTENTE_S]
        return len(recentes) >= 20 and sum(bool(f) for f in recentes) > len(recentes) / 2

    def estado(self):
        r = self.ultimo
        if r is None:
            return "AGUARDANDO A PLACA", "", NEUTRO
        if r["fase"] == "aprendendo":
            return ("●  APRENDENDO O NORMAL DESTE LUGAR",
                    f"deixe o cooler ligado e sem tocar: faltam {duracao(r['falta'])}", NEUTRO)
        if r.get("investigar"):
            return ("■  CHAMAR MANUTENÇÃO",
                    f"anomalia há {duracao(r['tempo_alerta_s'])}: investigar o equipamento", CRITICO)
        if self.episodio:
            ep = self.episodio
            if ep["fim"] - ep["inicio"] + N_AMOSTRAS / 400 > SUSTENTADO_S:
                return "■  VIBRAÇÃO ANORMAL CONTÍNUA", ep['pior']['detalhe'], CRITICO
            return "▲  PICO DETECTADO", ep['pior']['detalhe'], SERIO
        return "●  NORMAL", "nada fora do normal aprendido", BOM


# posicoes [esquerda, baixo, largura, altura] dos graficos
POS_UM = [0.08, 0.30, 0.64, 0.46]        # so o grafico da vibracao
POS_DOIS = [0.08, 0.50, 0.64, 0.26]      # vibracao, com o do modelo embaixo
POS_MODELO = [0.08, 0.29, 0.64, 0.15]    # nota do modelo (tecla M)


def montar_janela(painel):
    plt.rcParams.update({
        "figure.facecolor": SUPERFICIE, "axes.facecolor": SUPERFICIE,
        "axes.edgecolor": GRADE, "axes.labelcolor": TINTA_2,
        "xtick.color": TINTA_2, "ytick.color": TINTA_2, "font.size": 10,
        "axes.spines.top": False, "axes.spines.right": False,
    })
    fig = plt.figure(figsize=(13, 9))
    try:
        fig.canvas.manager.set_window_title("Detector adaptativo de vibração")
    except AttributeError:
        pass
    ax_topo = fig.add_axes([0.06, 0.84, 0.66, 0.12])
    ax_info = fig.add_axes([0.76, 0.42, 0.23, 0.54])
    ax = fig.add_axes(POS_UM)
    ax_an = fig.add_axes(POS_MODELO, sharex=ax)
    ax_log = fig.add_axes([0.06, 0.02, 0.92, 0.19])
    for a in (ax_topo, ax_info, ax_log):
        a.axis("off")

    titulo = ax_topo.text(0, 0.72, "", fontsize=22, fontweight="bold",
                          transform=ax_topo.transAxes, va="center")
    detalhe = ax_topo.text(0, 0.25, "", fontsize=12, color=TINTA_2,
                           transform=ax_topo.transAxes, va="center")
    aviso = ax_topo.text(0, -0.15, "", fontsize=11, color=SERIO, fontweight="bold",
                         transform=ax_topo.transAxes, va="center")
    info = ax_info.text(0.05, 0.98, "", fontsize=11, color=TINTA, va="top",
                        family="monospace", transform=ax_info.transAxes, linespacing=1.6)
    log = ax_log.text(0, 1.0, "", fontsize=10.5, color=TINTA, va="top",
                      family="monospace", transform=ax_log.transAxes)

    virgula = FuncFormatter(lambda v, _: f"{v:g}".replace(".", ","))
    for a in (ax, ax_an):
        a.grid(True, color=GRADE, linewidth=0.8)
        a.xaxis.set_major_formatter(virgula)
        a.yaxis.set_major_formatter(virgula)
    ax.set_xlim(-JANELA_S, 0)
    ax.set_ylabel("vibração total (g)")
    from matplotlib.lines import Line2D
    marcas = [
        Line2D([], [], marker="o", linestyle="none", color=CRITICO, markersize=7,
               label="alerta"),
        Line2D([], [], linestyle="none", label="tecla M: Isolation Forest"),
    ]
    ax.legend(handles=marcas, loc="lower left", bbox_to_anchor=(0, 1.02), ncol=2,
              frameon=False, fontsize=9.5, labelcolor=TINTA_2, handletextpad=0.4,
              columnspacing=1.8, borderaxespad=0)
    ax_an.text(0, 1.04, "nota do modelo: acima do limite, a combinação das 5 medidas é estranha",
               transform=ax_an.transAxes, fontsize=8.5, color=TINTA_2, va="bottom")

    def arrumar():
        if painel.mostrar_modelo:
            ax.set_position(POS_DOIS)
            ax_an.set_visible(True)
            ax.tick_params(labelbottom=False)
            ax.set_xlabel("")
        else:
            ax.set_position(POS_UM)
            ax_an.set_visible(False)
            ax.tick_params(labelbottom=True)
            ax.set_xlabel("segundos atrás")
    arrumar()
    ax_an.set_ylabel("anomalia\n(Isolation Forest)")
    ax_an.set_xlabel("segundos atrás")

    linha, = ax.plot([], [], color=SERIE, linewidth=2, zorder=3)
    pontos_alerta, = ax.plot([], [], "o", color=CRITICO, markersize=7, zorder=4)
    linha_an, = ax_an.plot([], [], color=ANOMALIA, linewidth=2, zorder=3)
    fora_an, = ax_an.plot([], [], "o", color=CRITICO, markersize=6, zorder=4)
    extras = []

    def atualizar(_):
        with painel.trava:
            agora = painel.agora
            pontos = list(painel.pontos)
            texto, sub, cor = painel.estado()
            eventos = list(painel.eventos)
            atualizacoes = list(painel.detector.atualizacoes)
            det = painel.detector
            corrente, rotacao = painel.corrente, painel.rotacao
            vibracao = painel.pontos[-1][1] if painel.pontos else None
            alarmes, simulando = painel.alarmes, painel.simulando
            deriva = painel.ultimo.get("deriva") if painel.ultimo else None

        titulo.set_text(texto)
        titulo.set_color(cor)
        detalhe.set_text(sub)
        if painel.conexao:
            aviso.set_text(painel.conexao.upper())
        elif painel.persistente():
            aviso.set_text("ANOMALIA PERSISTENTE: INVESTIGAR O EQUIPAMENTO")
        else:
            aviso.set_text("FALHA SIMULADA: vibração aumentada em 30% pelo software" if simulando else "")
        log.set_text("Registro\n" + ("\n".join(eventos) if eventos else "nada ainda"))

        ligado = (agora - det.inicio) if (agora is not None and det.inicio is not None) else 0
        desde = (agora - det.ultima_atualizacao) if det.ultima_atualizacao is not None else None
        linhas_info = [
            f"ligado há      {duracao(ligado)}",
            f"atualizações   {len(atualizacoes)}",
            f"última         {'há ' + duracao(desde) if desde is not None else '-'}",
            f"alarmes        {alarmes}",
            "",
            f"vibração       {num(vibracao) + ' g' if vibracao is not None else '-'}",
            f"corrente       {num(corrente, 0) + ' mA' if corrente is not None else '-'}",
            f"rotação        {num(rotacao, 0) + ' RPM' if rotacao else '-'}",
            "",
        ]
        if atualizacoes:
            a = atualizacoes[-1]
            linhas_info += [
                f"normal agora   {num(a['rms_media'])} g",
                f"vs. início     {(f'{deriva:+.1f}' if deriva is not None else '0.0').replace('.', ',')}%",
            ]
        info.set_text("\n".join(linhas_info))

        for artista in extras:
            artista.remove()
        extras.clear()
        if not pontos or agora is None:
            return []

        ts = [p[0] - agora for p in pontos]
        vs = [p[1] for p in pontos]
        linha.set_data(ts, vs)
        alertas = [bool(p[3]) for p in pontos]
        pontos_alerta.set_data([t for t, f in zip(ts, alertas) if f],
                               [v for v, f in zip(vs, alertas) if f])

        topo = max(vs)
        # A faixa do normal muda a cada atualizacao.
        for i, a in enumerate(atualizacoes):
            ini = a["t"] - agora
            fim = (atualizacoes[i + 1]["t"] - agora) if i + 1 < len(atualizacoes) else 0
            if fim < -JANELA_S:
                continue
            ini = max(ini, -JANELA_S)
            baixo, alto = a["rms_media"] - 2 * a["rms_desvio"], a["rms_media"] + 2 * a["rms_desvio"]
            extras.append(ax.fill_between([ini, fim], baixo, alto, color=FAIXA, zorder=1, linewidth=0))
            extras.append(ax.plot([ini, fim], [a["rms_media"]] * 2, color=TINTA_3, linewidth=1.5, zorder=2)[0])
            topo = max(topo, alto)
            if a["t"] - agora >= -JANELA_S:
                x = a["t"] - agora
                for eixo in (ax, ax_an):
                    extras.append(eixo.axvline(x, color=TINTA_3, linewidth=0.8, linestyle=":", zorder=1))
                rotulo = "aprendeu" if a["mudanca"] is None else "atualizou"
                extras.append(ax.text(x, 1.0, " " + rotulo, transform=ax.get_xaxis_transform(),
                                      fontsize=8, color=TINTA_3, va="top", ha="left"))
        if atualizacoes:
            a = atualizacoes[-1]
            extras.append(ax.text(-JANELA_S + 1, a["rms_media"] - 2 * a["rms_desvio"],
                                  " faixa do normal", color=TINTA_2, fontsize=9, va="top"))
        ax.set_ylim(0, topo * 1.25)

        # no grafico do modelo, vermelho so onde o proprio modelo passou o limite
        an = [(t, p[2], p[4]) for t, p in zip(ts, pontos) if p[2] is not None]
        if an:
            linha_an.set_data([x[0] for x in an], [x[1] for x in an])
            fora_an.set_data([x[0] for x in an if x[2]], [x[1] for x in an if x[2]])
            valores = [x[1] for x in an]
            limites = []
            for i, a in enumerate(atualizacoes):
                ini = max(a["t"] - agora, -JANELA_S)
                fim = (atualizacoes[i + 1]["t"] - agora) if i + 1 < len(atualizacoes) else 0
                if fim < -JANELA_S:
                    continue
                extras.append(ax_an.plot([ini, fim], [a["limite"]] * 2, color=CRITICO,
                                         linewidth=1.2, linestyle="--")[0])
                limites.append(a["limite"])
            baixo = min(valores + limites)
            alto = max(valores + limites)
            margem = (alto - baixo) * 0.15 or 0.05
            ax_an.set_ylim(baixo - margem, alto + margem)
            if limites:
                extras.append(ax_an.text(-JANELA_S + 1, limites[-1], " limite do modelo",
                                         color=CRITICO, fontsize=9, va="bottom"))
        else:
            linha_an.set_data([], [])
            fora_an.set_data([], [])
        return []

    def tecla(evento):
        if evento.key == "q":
            plt.close(fig)
        elif evento.key in ("m", "M"):
            painel.mostrar_modelo = not painel.mostrar_modelo
            arrumar()
            fig.canvas.draw_idle()

    fig.canvas.mpl_connect("key_press_event", tecla)
    return fig, atualizar


# --- fontes -------------------------------------------------------------

def janela_da_linha(linha):
    campos = linha.split(",")
    if len(campos) != len(COLUNAS) or campos[0] == "data_hora":
        return None
    janela = dict(zip(COLUNAS, campos))
    try:
        for c in COLUNAS[1:17]:
            janela[c] = float(janela[c])
        for c in ("corrente_ma", "rpm"):
            janela[c] = float(janela[c]) if janela[c] else float("nan")
    except ValueError:
        return None
    return janela


def simular_falha(janela, fator=1.3):
    janela = dict(janela)
    for e in "xyz":
        for k in ("rms", "pico", "adom"):
            janela[f"{e}_{k}"] = janela[f"{e}_{k}"] * fator
    return janela


def ler_placa(painel):
    """Le a placa e, se a conexao cair, avisa na tela e tenta de novo."""
    import serial
    while True:
        portas = sorted(glob.glob("/dev/cu.usbserial*") + glob.glob("/dev/cu.SLAB*")
                        + glob.glob("/dev/cu.wchusbserial*"))
        if not portas:
            painel.conexao = "placa não encontrada: confira o cabo USB"
            time.sleep(2)
            continue
        try:
            porta = serial.Serial(portas[0], 115200, timeout=1)
            porta.readline()
            painel.conexao = None
            while True:
                janela = janela_da_linha(porta.readline().decode(errors="replace").strip())
                if janela:
                    painel.adicionar(time.monotonic(), janela)
        except (serial.SerialException, OSError):
            painel.conexao = ("a conexão com a placa caiu. Feche o Serial Monitor do "
                              "Arduino IDE; tentando de novo...")
            time.sleep(2)


def reproduzir(painel, caminho, velocidade, falha):
    linhas = [l.strip() for l in open(caminho, encoding="utf-8") if not l.startswith("#")]
    t = 0.0
    for linha in linhas:
        janela = janela_da_linha(linha)
        if not janela:
            continue
        passo = N_AMOSTRAS / janela["taxa_hz"]
        t += passo
        simulada = falha is not None and falha <= t < falha + 60
        if simulada:
            janela = simular_falha(janela)
        painel.adicionar(t, janela, simulada)
        time.sleep(passo / velocidade)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reproduzir", metavar="CSV", help="toca uma gravacao em vez da placa")
    ap.add_argument("--velocidade", type=float, default=1.0)
    ap.add_argument("--falha", type=float, metavar="SEGUNDOS",
                    help="com --reproduzir: injeta 60 s de falha simulada nesse instante")
    args = ap.parse_args()

    painel = Painel()
    if args.reproduzir:
        alvo, extra = reproduzir, (painel, args.reproduzir, args.velocidade, args.falha)
    else:
        alvo, extra = ler_placa, (painel,)
    threading.Thread(target=alvo, args=extra, daemon=True).start()

    fig, atualizar = montar_janela(painel)
    _animacao = FuncAnimation(fig, atualizar, interval=300, cache_frame_data=False)  # noqa: F841
    try:
        plt.show()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
