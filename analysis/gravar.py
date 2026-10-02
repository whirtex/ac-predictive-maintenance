"""Grava uma sessao do cooler, do jeito mais simples possivel.

Use pelo atalho ./gravar, na pasta predictive-maintenance. Ele:

  1. acha a porta da placa sozinho;
  2. pergunta o nome da gravacao, que e o lugar onde o cooler esta (por
     exemplo mesa-a, mesa-b ou chao), ou Enter para um teste;
  3. grava em data/<nome>.csv (ou data/teste-HHMMSS.csv) e se recusa a
     gravar por cima de um arquivo que ja existe;
  4. abre o grafico da vibracao e da corrente numa janela separada;
  5. mostra o tempo e avisa quando der 10 minutos.

Ctrl+C encerra a gravacao e fecha o grafico.
"""

import glob
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime

import serial

PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DURACAO_SUGERIDA_S = 10 * 60


def achar_porta():
    portas = sorted(glob.glob("/dev/cu.usbserial*") + glob.glob("/dev/cu.SLAB*")
                    + glob.glob("/dev/cu.wchusbserial*"))
    if not portas:
        print("A placa não foi encontrada. Confira o cabo USB e tente de novo.")
        sys.exit(1)
    return portas[0]


def escolher_arquivo():
    resposta = input("Nome da gravação, o lugar do cooler (ex.: mesa-a, chao), "
                     "ou só Enter para um teste: ").strip()
    if resposta == "":
        return os.path.join(PASTA, "data", f"teste-{datetime.now():%H%M%S}.csv")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", resposta):
        print("Use só letras, números, - e _ no nome.")
        sys.exit(1)
    caminho = os.path.join(PASTA, "data", f"{resposta}.csv")
    if os.path.exists(caminho):
        print(f"Já existe uma gravação com esse nome (data/{resposta}.csv).")
        print("Escolha outro nome, ou apague esse arquivo antes.")
        sys.exit(1)
    return caminho


def main():
    caminho_porta = achar_porta()
    caminho = escolher_arquivo()
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    relativo = os.path.relpath(caminho, PASTA)

    porta = serial.Serial(caminho_porta, 115200, timeout=1)
    porta.reset_input_buffer()
    porta.readline()   # a primeira linha pode chegar cortada

    # O grafico roda num processo proprio: se ele travar ou for fechado,
    # a gravacao continua.
    grafico = subprocess.Popen(
        [sys.executable, os.path.join(PASTA, "analysis", "monitor.py"), "--seguir", caminho],
        start_new_session=True)

    print(f"\nGravando em {relativo}. Ctrl+C para parar.\n")

    inicio = time.monotonic()
    janelas = 0
    avisou = False
    avisou_silencio = False
    with open(caminho, "a", encoding="utf-8") as saida:
        try:
            while True:
                bruta = porta.readline()
                if not bruta:
                    if (janelas == 0 and not avisou_silencio
                            and time.monotonic() - inicio > 30):
                        avisou_silencio = True
                        print("  A placa não mandou nada em 30 s. Aperte o botão EN do ESP32"
                              " e espere uns 20 s; se nada mudar, pare com Ctrl+C.")
                    continue
                texto = bruta.decode(errors="replace").rstrip("\r\n")
                saida.write(texto + "\n")
                saida.flush()

                if texto.startswith("#"):
                    if "ALARME" in texto:
                        print(texto)
                    continue

                janelas += 1
                decorrido = time.monotonic() - inicio
                minutos, segundos = divmod(int(decorrido), 60)
                print(f"\r  {minutos:02d}:{segundos:02d}   {janelas} janelas", end="", flush=True)
                if decorrido >= DURACAO_SUGERIDA_S and not avisou:
                    avisou = True
                    print("\a\n  10 minutos! Pode parar com Ctrl+C.")
        except KeyboardInterrupt:
            pass

    grafico.send_signal(signal.SIGTERM)
    if janelas == 0:
        # Arquivo vazio nao pode ocupar o nome da gravacao.
        os.remove(caminho)
        print("\n\nNada foi gravado, e o arquivo vazio foi apagado. Confira a placa e"
              " rode ./gravar de novo.")
        return
    print(f"\n\nPronto: {janelas} janelas em {relativo}.")
    print("Para gravar em outro lugar, mude o cooler de lugar e rode ./gravar de novo.")


if __name__ == "__main__":
    main()
