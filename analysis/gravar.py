"""Grava uma sessao do cooler, do jeito mais simples possivel.

Use pelo atalho ./gravar, na pasta predictive-maintenance. Ele:

  1. acha a porta da placa sozinho;
  2. pergunta o numero da sessao (1, 2 ou 3), ou Enter para um teste;
  3. escolhe o arquivo (data/rep1.csv, ... ou data/teste-HHMMSS.csv) e
     se recusa a gravar por cima de uma sessao que ja existe;
  4. envia para a placa a repeticao e a condicao "normal", e envia de
     novo se a placa reiniciar;
  5. abre o grafico da vibracao e da corrente numa janela separada;
  6. mostra o tempo e avisa quando der 10 minutos.

Ctrl+C encerra a gravacao e fecha o grafico. Enquanto grava, o que for
digitado no terminal vai para a placa (por exemplo, c obstrucao).
"""

import glob
import os
import signal
import subprocess
import sys
import threading
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
    resposta = input("Qual sessão? Digite 1, 2 ou 3 (ou só Enter para um teste): ").strip()
    if resposta == "":
        nome = f"teste-{datetime.now():%H%M%S}.csv"
        return os.path.join(PASTA, "data", nome), None
    if resposta not in ("1", "2", "3"):
        print("Digite 1, 2, 3 ou só Enter.")
        sys.exit(1)
    caminho = os.path.join(PASTA, "data", f"rep{resposta}.csv")
    if os.path.exists(caminho):
        print(f"A sessão {resposta} já foi gravada (data/rep{resposta}.csv).")
        print("Para gravar de novo, apague esse arquivo antes.")
        sys.exit(1)
    return caminho, int(resposta)


def main():
    caminho_porta = achar_porta()
    caminho, repeticao = escolher_arquivo()
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    relativo = os.path.relpath(caminho, PASTA)

    porta = serial.Serial(caminho_porta, 115200, timeout=1)
    porta.reset_input_buffer()
    porta.readline()   # a primeira linha pode chegar cortada

    def enviar_rotulos():
        if repeticao is not None:
            porta.write(f"r {repeticao}\n".encode())
            time.sleep(0.2)
        porta.write(b"c normal\n")

    def repassar_teclado():
        for linha in sys.stdin:
            porta.write(linha.encode())

    threading.Thread(target=repassar_teclado, daemon=True).start()
    time.sleep(1.5)
    enviar_rotulos()

    # O grafico roda num processo proprio: se ele travar ou for fechado,
    # a gravacao continua.
    grafico = subprocess.Popen(
        [sys.executable, os.path.join(PASTA, "analysis", "monitor.py"), "--seguir", caminho],
        start_new_session=True)

    sessao = f"sessão {repeticao}" if repeticao else "teste"
    print(f"\nGravando {sessao} em {relativo}. Ctrl+C para parar.\n")

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
                    # Se a placa reiniciou, ela volta para a repeticao 1.
                    if (texto.startswith("# unidade=") and repeticao is not None
                            and not texto.endswith(f"repeticao={repeticao}")):
                        enviar_rotulos()
                    elif "ALARME" in texto:
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
        # Arquivo vazio nao pode ocupar o nome da sessao.
        os.remove(caminho)
        print("\n\nNada foi gravado, e o arquivo vazio foi apagado. Confira a placa e"
              " rode ./gravar de novo.")
        return
    print(f"\n\nPronto: {janelas} janelas em {relativo}.")
    if repeticao is not None and repeticao < 3:
        print(f"Desligue o ventilador por 1 minuto e depois grave a sessão {repeticao + 1}.")
    elif repeticao == 3:
        print("As três sessões estão gravadas. Próximo passo: ./treinar")


if __name__ == "__main__":
    main()
