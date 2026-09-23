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
    if coluna == "corrente_ma":
        return "corrente"
    if coluna == "rpm":
        return "rotação"
    eixo, tipo = coluna.split("_", 1)
    return f"{NOMES.get(tipo, tipo)} do eixo {eixo.upper()}"
