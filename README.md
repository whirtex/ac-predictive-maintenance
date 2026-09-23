# Monitoramento de vibração para manutenção preditiva

Protótipo da disciplina IBM3119, Projeto de Sistemas Embarcados (Ibmec, 2026).

O protótipo usa um ESP32 para medir a vibração de um ventilador de 12 V com um
acelerômetro ADXL345. Um INA219 mede a corrente e o firmware também prevê a leitura
da rotação pelo tacômetro do ventilador. A placa extrai características de cada
janela e envia linhas CSV pela porta USB ao computador. O script de análise compara
as características de vibração com uma referência aprendida na operação normal e
mostra qual delas mais se afastou dessa referência.

A vibração é o sinal principal e a entrada padrão do modelo, por orientação do
professor. Corrente e rotação ocupam colunas de apoio no CSV quando os respectivos
sensores estão conectados.

O ventilador serve como bancada para estudar componentes rotativos. Os ensaios
nesse ventilador não validam o sistema em um aparelho de ar-condicionado ou em um
compressor.

## O que funciona hoje

| Parte | Situação |
|---|---|
| Leitura da vibração (ADXL345) | Leitura demonstrada na bancada; a continuidade das amostras ainda precisa ser validada |
| Leitura da corrente (INA219) | Leitura demonstrada na bancada |
| Leitura da rotação (tacômetro) | Código disponível; falta confirmação na bancada final |
| Extração de características no ESP32 | Código disponível; a FFT foi conferida com sinais sintéticos |
| Captura, treino, figuras e detecção ao vivo | Scripts disponíveis; a cadeia completa ainda não foi avaliada com ensaios independentes |
| Falhas induzidas | Há uma medição preliminar de obstrução; falta publicar as rodadas completas e avaliar os modelos |

Até agora, este repositório não contém um conjunto de dados experimentais nem
métricas de detecção obtidas com as rodadas independentes. O valor preliminar da
obstrução está registrado em [`duvidas-professor.md`](duvidas-professor.md) e não
equivale a uma medida de desempenho do classificador.

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
externa: Adafruit INA219 1.2.3. O ADXL345 é lido diretamente por I²C. O sketch
`aquisicao_esp32` exige um arquivo local `credenciais.h`; copie
[`credenciais.h.exemplo`](firmware/aquisicao_esp32/credenciais.h.exemplo), preencha
a rede e a senha e mantenha `credenciais.h` fora do Git. O Wi-Fi é usado para
sincronizar o relógio por NTP; sem conexão, o CSV usa horários `boot+...`.

| Firmware (`firmware/`) | Para que serve |
|---|---|
| `aquisicao_esp32` | Extrai características e emite uma linha CSV por janela pela porta serial |
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
| `painel.py` | Painel da demonstração: gráfico ao vivo com a linha padrão e avisos, pelo modelo treinado ou por limite simples |
| `formato.py` | Colunas do CSV da placa, usadas pelos outros scripts |

### O que a placa calcula

O firmware configura o ADXL345 para 400 Hz e forma janelas de 512 amostras. Para
cada eixo calcula RMS, pico, curtose, frequência dominante e amplitude dessa
frequência. Remove a média da janela antes da FFT e aplica uma janela de Hann.
Corrente e rotação saem como colunas adicionais.

**Validação pendente da aquisição:** o I²C está configurado para 100 kHz, velocidade
para a qual o [datasheet do ADXL345](https://www.analog.com/media/en/technical-documentation/data-sheets/ADXL345.pdf)
recomenda uma taxa de saída de até 200 Hz. O FIFO em modo stream guarda 32 amostras;
o firmware ainda não mede perdas ou estouros durante o cálculo da FFT e a emissão
serial. A taxa incluída no CSV é estimada pela duração da janela e não comprova que
as 512 amostras sejam consecutivas. As características espectrais precisam dessa
verificação antes de fundamentar resultados quantitativos.

## Modelo

- **Detecção de anomalia:** Isolation Forest treinado só com janelas normais,
  sobre as 15 características de vibração. O limiar é definido pelo percentil 1
  dos escores de treino; isso não garante 1% de falsos alarmes em novos ensaios.
- **Método de comparação:** limite fixo no RMS total, igual à média mais 3
  desvios do normal de treino.
- **Característica destacada no alerta:** a mais distante da média normal, medida
  em desvios padrão. Esse indicador não identifica a causa física da falha nem
  explica a contribuição de cada variável para a decisão do Isolation Forest.
- **Resultado adicional:** Random Forest classificando as condições, com matriz de
  confusão.
- **Treino e teste:** separados por repetição. Por padrão, as repetições 1 e 2
  treinam, e a 3 avalia. A condição de falha é desfeita e refeita entre rodadas;
  o ventilador e a fixação do acelerômetro continuam os mesmos.
- **Métricas:** precisão, recall e F1 na detecção; F1 por classe na classificação.

O protocolo prevê obstrução (entrada de ar tapada), desbalanceamento (massa presa
numa pá) e, caso o mecanismo seja montado, atrito. O script descarta por padrão os
primeiros 180 s de cada trecho contínuo de condição e repetição.

## Como usar

Dentro de `predictive-maintenance/`, uma vez só:

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r analise/requirements.txt
```

Antes de gravar `aquisicao_esp32` pela Arduino IDE, crie as credenciais locais:

```sh
cp firmware/aquisicao_esp32/credenciais.h.exemplo firmware/aquisicao_esp32/credenciais.h
```

Edite o novo arquivo com a rede Wi-Fi do laboratório. A porta serial deve ser
substituída pela porta real do ESP32 nos comandos abaixo.

Gravar os ensaios, com o `aquisicao_esp32` na placa e o monitor serial fechado:

```
python analise/captura_serial.py /dev/cu.usbserial-XXXX dados/rep1.csv
```

No mesmo terminal, informe `u A`, `r 1` e `c normal`. Atualize `c` quando a
condição mudar e `r` antes de cada repetição. Faça rodadas independentes para a
repetição 3; mantenha uma identificação clara dos arquivos e das condições. O
roteiro físico está em [`montagem.md`](montagem.md).

Treinar e gerar as figuras:

```
python analise/treino.py dados/*.csv            # figuras em português
python analise/treino.py dados/*.csv --ingles   # figuras em inglês, para o artigo
```

Os resultados são gravados em `resultados/`: `relatorio.txt`,
`vibracao_no_tempo.png`, `comparacao_metodos.png` e `modelo.joblib`. O arquivo
`confusao.png` só é criado quando há dados de pelo menos duas condições nas
repetições de treino. Confira no relatório quantas janelas restaram após o
descarte inicial de cada trecho.

Painel da demonstração. Mostra a vibração ao vivo, a linha padrão, e avisa cada
pico ou vibração anormal contínua, dizendo o que desviou. Tem dois modos:

```
# modo modelo: usa o modelo treinado; aquisicao_esp32 na placa
python analise/painel.py /dev/cu.usbserial-XXXX --modelo

# modo limite: aprende a linha padrão em 15 s, sem modelo; demo_vibracao na placa
python analise/painel.py /dev/cu.usbserial-XXXX

# toca uma gravação no ritmo real, para ensaiar ou se a placa falhar
python analise/painel.py --reproduzir dados/rep3.csv --modelo

# dados falsos no modo limite, para testar sem a placa
python analise/painel.py --simular
```

No modo modelo, o gráfico de baixo é o grau de anomalia calculado pelo Isolation
Forest, com o limite dele: é exatamente o que o modelo usa para decidir.

A detecção pelo modelo também existe só em texto, no terminal:

```
python analise/ao_vivo.py /dev/cu.usbserial-XXXX
```

## Customizações

O que foi desenvolvido além do uso padrão das bibliotecas e da IDE:

- **Leitura direta do ADXL345.** O firmware configura registradores e usa o FIFO
  em modo stream. A continuidade das amostras ainda precisa ser medida.
- **FFT na placa.** Implementação própria da FFT radix-2, com janela de Hann e
  correção do ganho da janela, para que a amplitude saia em g. A conta foi
  conferida com senos de amplitude e frequência conhecidas.
- **Taxa estimada por janela.** A conversão de frequência usa a duração medida
  pelo ESP32. Essa estimativa não substitui a checagem de amostras perdidas.
- **Rotulagem durante o ensaio.** Comandos pela serial (`c`, `r`, `u`) gravam em
  cada linha a condição e a repetição. É isso que permite separar treino e teste
  por repetição.
- **Hora por NTP em vez de relógio externo.** O módulo DS1302 foi descartado
  depois de medido: contava seis vezes mais rápido que o tempo real.
- **Avisos de falha de sensor.** O firmware avisa quando o ADXL345 ou o INA219
  param de responder, tenta reiniciar o ADXL345 e tenta reconectar o INA219 a
  cada dois segundos.
- **Tacômetro por interrupção**, contando dois pulsos por volta.
- **Corrente pela média da janela.** O motor sem escovas puxa corrente em pulsos,
  e uma leitura solta varia mais de 80 mA sem falha nenhuma.
- **Scripts de gravação, treino e detecção ao vivo**, em `analise/`.

## Limitações

- Os ensaios são em bancada, com falhas aplicadas por fora. Massa numa pá não é
  rolamento de compressor desgastado.
- Há um único ventilador, então treino e teste vêm da mesma unidade.
- A configuração atual de 400 Hz em I²C de 100 kHz e a ausência de contagem de
  estouros do FIFO impedem afirmar que a série amostrada seja contínua.
- O envio por MQTT e o armazenamento local planejados para operação sem USB ainda
  não foram implementados. A coleta atual depende da porta serial e do computador.
- Ainda faltam dados publicados de rodadas independentes para estimar precisão,
  recall, F1 e taxa de falsos alarmes em operação nova.

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
