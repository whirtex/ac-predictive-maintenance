# Manutenção preditiva de ar-condicionado por vibração

Protótipo da disciplina IBM3119, Projeto de Sistemas Embarcados (Ibmec, 2026).

Um ESP32 lê a vibração de um ventilador de 12 V com um acelerômetro, calcula as
características de cada janela na própria placa e manda o resultado para o
computador. Lá, um modelo treinado só com a operação normal decide se cada janela
é normal ou anômala, e aponta qual característica de vibração mais se afastou do
normal.

O ventilador é da mesma classe do ventilador da unidade condensadora de um
ar-condicionado. Os resultados caracterizam o método em bancada; não validam o
sistema num aparelho real.

## O que funciona hoje

| Parte | Situação |
|---|---|
| Leitura da vibração (ADXL345) | Funcionando e validada na bancada |
| Leitura da corrente (INA219) | Funcionando |
| Leitura da rotação (tacômetro do ventilador) | Firmware pronto, ainda não testado na bancada |
| Firmware de coleta com características na placa | Compila; conta da FFT conferida com sinais sintéticos |
| Gravação, treino e detecção ao vivo | Scripts prontos, testados com dados sintéticos |
| Ensaios com falhas induzidas | Obstrução medida (6,2 desvios acima do ruído); falta gravar o conjunto completo |

## Hardware

| Componente | Função |
|---|---|
| ESP32-WROVER-DEV | Microcontrolador, com Wi-Fi para a hora por NTP |
| ADXL345 (placa GY-291) | Acelerômetro de 3 eixos, colado na lateral do ventilador |
| INA219 | Corrente do ventilador, em série com a alimentação |
| Ventilador de 12 V, 80 × 80 × 25 mm, 3 fios | Equipamento de ensaio; o fio amarelo é o tacômetro |
| Fonte regulada de 12 V, 1 A, e adaptador P4 com borne | Alimentação do ventilador |
| Resistor de 10 kΩ | Pull-up do tacômetro |
| Protoboard, jumpers e tábua de madeira | Montagem; o ventilador fica colado em pé na tábua |

### Ligação

| De | Para |
|---|---|
| ADXL345 `SDA` / `SCL` | GPIO 21 / GPIO 22 |
| ADXL345 `VCC` e `CS` | 3,3 V (o `CS` em 3,3 V liga o modo I2C) |
| ADXL345 `GND` e `SDO` | GND (o `SDO` em GND fixa o endereço `0x53`) |
| INA219 `SDA` / `SCL` / `VCC` / `GND` | GPIO 21 / GPIO 22 / 3,3 V / GND |
| `+` da fonte → `VIN+` do INA219 → `VIN−` → vermelho do ventilador | Caminho da corrente medida |
| Amarelo do ventilador | GPIO 18, com 10 kΩ para 3,3 V |
| GND do ESP32, preto do ventilador e `−` da fonte | Mesmo ponto |

As fileiras `+` e `−` da protoboard só recebem 3,3 V e GND se houver um jumper
do `3V3` e do `GND` do ESP32 até elas. O passo a passo completo, com os testes de
cada etapa, está em [`montagem.md`](montagem.md).

## Software

Placa: ESP32 Wrover Module, core `esp32` 3.3.11, Arduino IDE 2.3.10. Biblioteca
externa: Adafruit INA219 1.2.3. O ADXL345 não usa biblioteca.

| Firmware (`firmware/`) | Para que serve |
|---|---|
| `aquisicao_esp32` | Coleta dos dados de treino: uma linha CSV por janela, com rótulo |
| `demo_vibracao` | Gráfico ao vivo da vibração no Serial Plotter, para demonstração |
| `teste_obstrucao_vibracao` | Compara a vibração com a entrada de ar livre e tapada |
| `teste_obstrucao` | A mesma comparação, na corrente |
| `teste_rotacao` | Lê o tacômetro e compara a rotação livre e tapada |
| `corrente_ao_vivo` | Confere a ligação do INA219 |
| `scanner_i2c` | Confere solda e ligação dos sensores I2C |
| `teste_leitura_adxl345` | Conta leituras certas e erradas do ADXL345, para achar mau contato |

| Análise (`analise/`) | Para que serve |
|---|---|
| `captura_serial.py` | Grava a saída da placa num CSV e repassa os comandos de rótulo |
| `treino.py` | Treina, avalia e gera figuras, relatório e o modelo salvo |
| `ao_vivo.py` | Detecção ao vivo com o modelo salvo |

### O que a placa calcula

A cada janela de 512 amostras a 400 Hz (cerca de 1,3 s), para cada eixo: RMS,
pico, curtose, frequência dominante e amplitude dessa frequência. A média da janela
sai antes das contas, porque é a gravidade. A FFT usa janela de Hann. Corrente e
rotação saem como colunas extras.

## Modelo

- **Detecção de anomalia:** Isolation Forest treinado só com janelas normais,
  sobre as 15 características de vibração. O limiar aceita 1% de falso alarme nas
  janelas normais de treino.
- **Método de comparação:** limite fixo no RMS total, igual à média mais 3
  desvios do normal de treino.
- **Qual medição desviou:** em cada alerta, a característica mais distante do
  normal, medida em desvios.
- **Resultado adicional:** Random Forest classificando as condições, com matriz de
  confusão.
- **Treino e teste:** separados por repetição. As repetições 1 e 2 treinam, a 3
  avalia. Cada repetição desfaz e refaz a falha, então nenhuma janela de teste vem
  da mesma montagem de uma janela de treino.
- **Métricas:** precisão, recall e F1 na detecção; F1 por classe na classificação.

As condições induzidas são obstrução (entrada de ar tapada), desbalanceamento
(massa presa numa pá) e, se o mecanismo ficar pronto, atrito.

## Como usar

Dentro de `predictive-maintenance/`, uma vez só:

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r analise/requirements.txt
```

Gravar os ensaios, com o `aquisicao_esp32` na placa e o monitor serial fechado:

```
python analise/captura_serial.py /dev/cu.usbserial-XXXX dados/rep1.csv
```

No mesmo terminal, digite `r 1` e depois `c normal`, `c obstrucao`,
`c desbalanceamento` a cada troca de condição. O roteiro está em `montagem.md`.

Treinar e gerar as figuras:

```
python analise/treino.py dados/*.csv            # figuras em português
python analise/treino.py dados/*.csv --ingles   # figuras em inglês, para o artigo
```

Tudo vai para `resultados/`: `relatorio.txt`, `vibracao_no_tempo.png`,
`comparacao_metodos.png`, `confusao.png` e `modelo.joblib`.

Demonstração ao vivo, com o modelo já treinado:

```
python analise/ao_vivo.py /dev/cu.usbserial-XXXX
```

## Customizações

O que foi desenvolvido além do uso padrão das bibliotecas e da IDE:

- **Driver próprio do ADXL345.** A leitura fala direto com os registradores, com
  a fila interna do sensor em modo stream. Assim a taxa de 400 Hz fica sob
  controle, e nenhuma amostra se perde entre duas consultas.
- **FFT na placa.** Implementação própria da FFT radix-2, com janela de Hann e
  correção do ganho da janela, para que a amplitude saia em g. A conta foi
  conferida com senos de amplitude e frequência conhecidas.
- **Taxa medida, não assumida.** A frequência de cada janela é convertida com a
  taxa real do sensor naquela janela, porque o ADXL345 tem tolerância na taxa.
- **Rotulagem durante o ensaio.** Comandos pela serial (`c`, `r`, `u`) gravam em
  cada linha a condição e a repetição. É isso que permite separar treino e teste
  por repetição.
- **Hora por NTP em vez de relógio externo.** O módulo DS1302 foi descartado
  depois de medido: contava seis vezes mais rápido que o tempo real.
- **Alarme de falha de sensor.** Se o ADXL345 ou o INA219 param de responder, o
  firmware avisa e tenta reconectar sozinho, sem travar a coleta.
- **Tacômetro por interrupção**, contando dois pulsos por volta.
- **Corrente pela média da janela.** O motor sem escovas puxa corrente em pulsos,
  e uma leitura solta varia mais de 80 mA sem falha nenhuma.
- **Scripts de gravação, treino e detecção ao vivo**, em `analise/`.

## Limitações

- Os ensaios são em bancada, com falhas aplicadas por fora. Massa numa pá não é
  rolamento de compressor desgastado.
- Há um único ventilador, então treino e teste vêm da mesma unidade.
- O artigo descreve o envio por MQTT, que ainda não está implementado: por
  enquanto os dados vão por USB para o computador.

## Documentos

| Arquivo | Conteúdo |
|---|---|
| `predictive-maintenance.tex` | Artigo, em inglês, no modelo do SBrT |
| `predictive-maintenance-pt.md` | Tradução de apoio do artigo |
| `montagem.md` | Montagem da bancada e roteiro dos ensaios |
| `decisoes-do-projeto.md` | Decisões tomadas, com o porquê, e o que está em aberto |
| `plano-do-prototipo.md` | Plano e lista de materiais |
| `requirements.md`, `specifications.md` | Requisitos e especificação |
| `duvidas-professor.md` | Perguntas levadas ao professor e as respostas |
