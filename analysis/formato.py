"""Formato da linha CSV emitida pelo aquisicao_esp32.

Fica num arquivo proprio para que o treino, a deteccao ao vivo e o
painel usem a mesma lista sem um importar o outro.
"""

COLUNAS = [
    "data_hora", "unidade", "condicao", "repeticao", "taxa_hz",
    "x_rms", "x_pico", "x_curtose", "x_fdom", "x_adom",
    "y_rms", "y_pico", "y_curtose", "y_fdom", "y_adom",
    "z_rms", "z_pico", "z_curtose", "z_fdom", "z_adom",
    "corrente_ma", "rpm",
]

VIBRACAO = [c for c in COLUNAS if c[:2] in ("x_", "y_", "z_")]
APOIO = ["corrente_ma", "rpm"]

# Nome de cada caracteristica em palavras, para as mensagens de alerta.
NOMES = {"rms": "RMS", "pico": "pico", "curtose": "curtose",
         "fdom": "frequência dominante", "adom": "amplitude da frequência dominante"}


def nome_legivel(coluna):
    if coluna in NOMES_TOTAIS:
        return NOMES_TOTAIS[coluna]
    if coluna == "corrente_ma":
        return "corrente"
    if coluna == "rpm":
        return "rotação"
    eixo, tipo = coluna.split("_", 1)
    return f"{NOMES.get(tipo, tipo)} do eixo {eixo.upper()}"


# --- medidas totais -----------------------------------------------------
# Somam os tres eixos num valor so. Nao dependem de como a vibracao se
# divide entre X, Y e Z, que muda quando o ventilador pousa diferente na
# mesa: nas tres sessoes gravadas, o RMS do eixo X variou de 0,075 a
# 0,146 g, enquanto o total ficou entre 0,145 e 0,154 g.

TOTAIS = ["rms_total", "pico_total", "adom_total", "curtose_media", "fdom"]

NOMES_TOTAIS = {
    "rms_total": "vibração total",
    "pico_total": "pico da vibração",
    "adom_total": "força da frequência dominante",
    "curtose_media": "trancos (curtose)",
    "fdom": "frequência dominante",
}


def derivar_janela(v):
    """As 5 medidas totais de uma janela (dicionario com as colunas)."""
    import math
    soma = lambda tipo: math.sqrt(sum(float(v[f"{e}_{tipo}"]) ** 2 for e in "xyz"))
    fdoms = sorted(float(v[f"{e}_fdom"]) for e in "xyz")
    return {
        "rms_total": soma("rms"),
        "pico_total": soma("pico"),
        "adom_total": soma("adom"),
        "curtose_media": sum(float(v[f"{e}_curtose"]) for e in "xyz") / 3,
        "fdom": fdoms[1],
    }


def derivar_tabela(df):
    """Acrescenta as 5 medidas totais a uma tabela do pandas."""
    import numpy as np
    for tipo in ("rms", "pico", "adom"):
        df[f"{tipo}_total"] = np.sqrt(sum(df[f"{e}_{tipo}"] ** 2 for e in "xyz"))
    df["curtose_media"] = sum(df[f"{e}_curtose"] for e in "xyz") / 3
    df["fdom"] = df[[f"{e}_fdom" for e in "xyz"]].median(axis=1)
    return df
