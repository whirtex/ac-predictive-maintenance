"""Avalia o detector de duas bases nas tres sessoes gravadas.

As sessoes (data/rep1.csv a rep3.csv) sao do ventilador em operacao
normal. As falhas sao simuladas por software sobre elas, e o relatorio
diz isso. Mede:

  1. alarme falso no normal, depois do aprendizado inicial;
  2. falha brusca simulada (+30% na vibracao, no pico e na forca da
     frequencia dominante, por 60 s), injetada em varios momentos de cada
     sessao: fracao das janelas da falha que viraram alarme, e quem
     disparou (so a regua, so o modelo, os dois);
  3. mudanca lenta simulada (1%, 1,5% e 2% por minuto): fracao de janelas
     em alarme durante a subida e o "vs. inicio" no fim;
  4. a mesma coisa com uma base fixa, aprendida uma vez e nunca
     atualizada, para medir o que a adaptacao muda.

Saidas em results/: avaliacao_duas_bases.txt e avaliacao_lenta.png.

Uso (na pasta predictive-maintenance):
    .venv/bin/python analysis/avaliar_duas_bases.py
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

from adaptativo import DetectorAdaptativo  # noqa: E402
from formato import COLUNAS  # noqa: E402

PASTA = Path(__file__).resolve().parent.parent
APRENDIZADO_S = 120
FALHA_S = 60
FATOR_FALHA = 1.30
NUNCA = 10 ** 9     # atualiza_s da base fixa: nunca reaprende


def carregar(r):
    janelas = []
    t = 0.0
    with open(PASTA / "data" / f"rep{r}.csv", encoding="utf-8") as f:
        for linha in csv.reader(f):
            if not linha or linha[0].startswith("#") or len(linha) != len(COLUNAS):
                continue
            if linha[0] == "data_hora":
                continue
            j = dict(zip(COLUNAS, linha))
            try:
                t += 512 / float(j["taxa_hz"])
            except ValueError:
                continue
            janelas.append((t, j))
    return janelas


def escalar(j, fator):
    j = dict(j)
    for e in "xyz":
        for k in ("rms", "pico", "adom"):
            j[f"{e}_{k}"] = float(j[f"{e}_{k}"]) * fator
    return j


def rodar(janelas, fator=lambda t: 1.0, atualiza_s=None):
    det = DetectorAdaptativo() if atualiza_s is None else DetectorAdaptativo(atualiza_s=atualiza_s)
    saida = []
    for t, j in janelas:
        f = fator(t)
        r = det.adicionar(t, escalar(j, f) if f != 1.0 else j)
        motivo = r.get("motivo") or ""
        saida.append({
            "t": t, "fase": r["fase"], "fora": bool(r.get("fora")),
            "regua": "régua" in motivo, "modelo": "modelo" in motivo,
            "vib": r["medidas"]["rms_total"], "base": r.get("rms_media", np.nan),
            "deriva": r.get("deriva", np.nan), "investigar": bool(r.get("investigar")),
        })
    return saida, det


def pct(x):
    return f"{100 * x:5.1f}%"


def main():
    sessoes = {r: carregar(r) for r in (1, 2, 3)}

    print("DETECTOR DE DUAS BASES: avaliacao nas tres sessoes gravadas")
    print("Falhas simuladas por software sobre gravacoes normais reais.\n")

    # --- 1 e 4. alarme falso: adaptativo e base fixa ----------------------
    print("== 1. ALARME FALSO NO NORMAL (depois dos 2 min de aprendizado)")
    total = {"adaptativa": [0, 0], "fixa": [0, 0]}
    for r, jan in sessoes.items():
        linha = f"  sessao {r} ({jan[-1][0] / 60:4.1f} min):"
        for nome, atual in (("adaptativa", None), ("fixa", NUNCA)):
            res, _ = rodar(jan, atualiza_s=atual)
            det = [x for x in res if x["fase"] == "detectando"]
            fa = sum(x["fora"] for x in det)
            total[nome][0] += fa
            total[nome][1] += len(det)
            linha += f"   base {nome}: {pct(fa / len(det))} ({fa} de {len(det)})"
        print(linha)
    for nome, (fa, n) in total.items():
        print(f"  total, base {nome}: {pct(fa / n)} ({fa} de {n} janelas)")

    # --- 2. falha brusca simulada -----------------------------------------
    print("\n== 2. FALHA BRUSCA SIMULADA (+30% por 60 s, a cada 5 min de cada sessao)")
    cont = {"alarme": 0, "regua": 0, "modelo": 0, "ambos": 0, "janelas": 0, "injecoes": 0,
            "detectadas": 0, "investigar": 0}
    for r, jan in sessoes.items():
        fim = jan[-1][0]
        for inicio in np.arange(300, fim - 2 * FALHA_S, 300):
            res, _ = rodar(jan, lambda t, i=inicio: FATOR_FALHA if i <= t < i + FALHA_S else 1.0)
            dentro = [x for x in res if inicio <= x["t"] < inicio + FALHA_S]
            cont["injecoes"] += 1
            cont["detectadas"] += any(x["fora"] for x in dentro)
            cont["janelas"] += len(dentro)
            cont["alarme"] += sum(x["fora"] for x in dentro)
            cont["regua"] += sum(x["regua"] and not x["modelo"] for x in dentro)
            cont["modelo"] += sum(x["modelo"] and not x["regua"] for x in dentro)
            cont["ambos"] += sum(x["regua"] and x["modelo"] for x in dentro)
            cont["investigar"] += any(x["investigar"] for x in res)
    n = cont["janelas"]
    print(f"  {cont['injecoes']} falhas injetadas, {cont['detectadas']} detectadas")
    print(f"  janelas da falha em alarme: {pct(cont['alarme'] / n)} ({cont['alarme']} de {n})")
    print(f"    so pela regua:  {pct(cont['regua'] / n)}")
    print(f"    so pelo modelo: {pct(cont['modelo'] / n)}")
    print(f"    pelos dois:     {pct(cont['ambos'] / n)}")
    print(f"  pedidos de investigacao (mudanca persistente): {cont['investigar']}")

    # --- 3. mudanca lenta simulada ----------------------------------------
    # comeca no minuto 10 da sessao 3, depois da queda natural do inicio
    print("\n== 3. MUDANCA LENTA SIMULADA (sessao 3, a partir do minuto 10;"
          " subida comeca 4 min depois)")
    base_jan = [(t - 600, j) for t, j in sessoes[3] if t >= 600]
    curvas = {}
    for taxa in (0.010, 0.015, 0.020):
        res, _ = rodar(base_jan, lambda t, k=taxa: 1.0 + k * max(0.0, t - 240) / 60)
        subida = [x for x in res if x["t"] >= 240 and x["fase"] == "detectando"]
        derivas = [x["deriva"] for x in res if not np.isnan(x["deriva"])]
        curvas[taxa] = res
        print(f"  {100 * taxa:.1f}% por minuto: alarme em {pct(np.mean([x['fora'] for x in subida]))}"
              f" das janelas da subida; vs. inicio no fim: {derivas[-1]:+.1f}%")
        pedido = [x["t"] for x in res if x["investigar"]]
        print("      investigar: " + (f"pedido {(pedido[0] - 240) / 60:.1f} min depois do"
                                      " comeco da subida" if pedido else "nunca"))
        resf, _ = rodar(base_jan, lambda t, k=taxa: 1.0 + k * max(0.0, t - 240) / 60,
                        atualiza_s=NUNCA)
        subf = [x for x in resf if x["t"] >= 240 and x["fase"] == "detectando"]
        print(f"      com base fixa: alarme em {pct(np.mean([x['fora'] for x in subf]))}"
              " das janelas da subida")

    # --- figura: mudanca lenta a 1,5% por minuto ---------------------------
    res = curvas[0.015]
    t = np.array([x["t"] for x in res]) / 60
    vib = np.array([x["vib"] for x in res])
    base = np.array([x["base"] for x in res])
    fora = np.array([x["fora"] for x in res])
    det = DetectorAdaptativo()
    for tt, j in base_jan:
        det.adicionar(tt, j)
        if det.referencia:
            break
    ref = det.referencia
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
    fig, ax = plt.subplots(figsize=(6.4, 2.8))
    ax.plot(t, vib, color="#2a78d6", linewidth=1, label="vibration")
    ax.plot(t, base, color="#52514e", linewidth=1.6, label="adaptive baseline")
    ax.axhline(ref, color="#1baf7a", linewidth=1.4, linestyle="--", label="installation reference")
    ax.plot(t[fora], vib[fora], "o", color="#d03b3b", markersize=2.5, label="alarm")
    ax.set_xlabel("time (min)")
    ax.set_ylabel("total RMS (g)")
    ax.grid(True, color="#e4e3df", linewidth=0.6)
    ax.legend(frameon=False, ncol=4, loc="lower left", bbox_to_anchor=(0, 1.0), fontsize=8)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    fig.tight_layout()
    fig.savefig(PASTA / "results" / "avaliacao_lenta.png", dpi=200)
    plt.close(fig)
    print("\nfigura: results/avaliacao_lenta.png (1,5% por minuto)")


if __name__ == "__main__":
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        main()
    texto = buffer.getvalue()
    (PASTA / "results").mkdir(exist_ok=True)
    (PASTA / "results" / "avaliacao_duas_bases.txt").write_text(texto, encoding="utf-8")
    sys.stdout.write(texto)
