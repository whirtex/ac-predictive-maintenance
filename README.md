# Manutenção preditiva de equipamentos de ar-condicionado

Protótipo da disciplina IBM3119, Projeto de Sistemas Embarcados (Ibmec, 2026).

O objetivo é um sistema embarcado que monitora a condição de equipamentos de
ar-condicionado em operação contínua, como os de salas de servidores, hospitais e
shelters de telecomunicação, e detecta desvios que possam orientar a manutenção.
A vibração é o sinal principal e a única entrada do detector, por orientação do
professor. Corrente e rotação são registradas como apoio. A primeira versão detecta
anomalias. Ela não diz qual é a falha nem estima a vida útil restante.

O desenvolvimento tem duas etapas. **Na bancada**, um ventilador de 12 V permite
montar a cadeia de aquisição e provocar alterações controladas. **No
equipamento-alvo**, a instalação dos sensores num ar-condicionado ainda depende de
acesso ao aparelho e de uma montagem elétrica adequada. Os resultados da bancada não
demonstram desempenho num ar-condicionado real.

Como funciona hoje: um ESP32 lê o ADXL345, o INA219 e o tacômetro, calcula as
características de cada janela de ~1,23 s e envia uma linha CSV pela USB. No
computador, um **detector adaptativo de duas bases** aprende o normal do lugar nos
primeiros 2 minutos, reaprende a cada minuto e guarda a base da instalação para
mostrar a deriva. O MQTT fica para a instalação em campo (a rede da faculdade exige
login por página web, que a placa não consegue fazer).

## Estado da bancada experimental

| Parte | Situação |
|---|---|
| Vibração (ADXL345) | Funcionando; a continuidade das amostras dentro da janela ainda não foi medida |
| Corrente (INA219) | Funcionando, média por janela (148 a 153 mA nas sessões) |
| Rotação (tacômetro) | Lê, mas conta de 25% a 52% a mais; a rotação confiável vem do pico de vibração (~46,4 Hz, ~2780 rpm) |
| Características no ESP32 | Funcionando; a FFT foi conferida com senos conhecidos |
| Gravação, painel e detector adaptativo | Funcionando ao vivo na bancada |
| Dados | Três sessões normais independentes em `data/` (12,3, 21,5 e 37,1 min) |
| Falhas | Simuladas por software sobre as sessões normais; perturbações físicas só nos testes ao vivo. Gravações de desbalanceamento, atrito e obstrução ficam para a próxima etapa |

## Hardware da bancada experimental

| Componente | Função |
|---|---|
| ESP32-WROVER-DEV | Microcontrolador, com Wi-Fi para a hora por NTP |
| ADXL345 (placa GY-291) | Acelerômetro de 3 eixos, colado na lateral do ventilador |
| INA219 | Corrente do ventilador, em série com a alimentação |
| Ventilador de 12 V, 80 × 80 × 25 mm, 3 fios | Equipamento de ensaio; o fio amarelo é o tacômetro |
| Fonte regulada de 12 V, 1 A, e adaptador P4 com borne | Alimentação do ventilador |
| Resistor de 10 kΩ | Pull-up do tacômetro |
| Protoboard, jumpers e tábua de madeira | Montagem; o ventilador fica colado em pé na tábua |

### Ligações da bancada

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
cada etapa, está em [`docs/montagem.md`](docs/montagem.md).

## Software

Placa: ESP32 Wrover Module, core `esp32` 3.3.11, Arduino IDE 2.3.10. Biblioteca
externa: Adafruit INA219 1.2.3. O ADXL345 é lido diretamente por I²C. O sketch
`aquisicao_esp32` exige um arquivo local `credenciais.h`; copie
[`credenciais.h.exemplo`](firmware/aquisicao_esp32/credenciais.h.exemplo), preencha
a rede e a senha e mantenha `credenciais.h` fora do Git. O Wi-Fi só sincroniza o
relógio por NTP; sem conexão, o CSV usa horários `boot+...`.

No computador: Python 3 com `numpy`, `pandas`, `scikit-learn`, `matplotlib` e
`pyserial` (lista em `analysis/requirements.txt`).

| Firmware (`firmware/`) | Para que serve |
|---|---|
| `aquisicao_esp32` | Extrai características e emite uma linha CSV por janela pela porta serial |

Os sketches de teste, usados para montar e conferir a bancada, ficam em
`firmware/tests/`:

| Teste (`firmware/tests/`) | Para que serve |
|---|---|
| `demo_vibracao` | Gráfico ao vivo da vibração no Serial Plotter, para demonstração |
| `teste_obstrucao_vibracao` | Compara a vibração com a entrada de ar livre e tapada |
| `teste_obstrucao` | A mesma comparação, na corrente |
| `teste_rotacao` | Lê o tacômetro e compara a rotação livre e tapada |
| `corrente_ao_vivo` | Confere a ligação do INA219 |
| `scanner_i2c` | Confere solda e ligação dos sensores I2C |
| `teste_leitura_adxl345` | Conta leituras certas e erradas do ADXL345, para achar mau contato |

| Análise (`analysis/`) | Para que serve |
|---|---|
| `adaptativo.py` | O detector de duas bases (Isolation Forest + régua, linha de base adaptativa, referência da instalação) |
| `painel_adaptativo.py` | Painel da apresentação, ao vivo ou tocando uma gravação |
| `gravar.py` | Grava uma sessão da placa em `data/` e mostra o gráfico durante a gravação |
| `monitor.py` | Gráfico simples da vibração, com a corrente no canto |
| `avaliar_duas_bases.py` | Avaliação offline do detector nas três sessões (números do artigo) |
| `videos_duas_bases.py` | Vídeos da mudança brusca, da mudança lenta e dos dois juntos |
| `figura_arquitetura.py` | Diagrama da arquitetura usado no artigo |
| `formato.py` | Colunas do CSV da placa e as 5 medidas totais |
| `legacy/` | Primeira versão (`treino.py`, `painel.py`, `ao_vivo.py`, `captura_serial.py`): modelo treinado uma vez, mantido como comparação |

### O que a placa calcula

O firmware configura o ADXL345 para 400 Hz, com o FIFO em modo stream, e forma
janelas de 512 amostras (~1,23 s a 417 Hz medidos). Para cada eixo calcula RMS
(sem a média), pico, curtose e, com janela de Hann e FFT de 512 pontos, a frequência
dominante e a amplitude dela. Corrente (média da janela) e rotação saem como colunas
adicionais. São 19 colunas por linha.

## Modelo: detector de duas bases

O detector usa **5 medidas que não dependem da orientação do sensor**: a soma
vetorial dos RMS, dos picos e das amplitudes dominantes dos três eixos, a curtose
média e a frequência dominante mediana. Cada janela passa por dois testes, e basta
um para virar alarme:

- **Isolation Forest** (150 árvores, sobre as 5 medidas padronizadas). O limiar é o
  quantil de 0,2% das notas do normal. Só acusa se marcar duas janelas seguidas e
  alguma medida estiver a pelo menos 3 desvios do normal.
- **Régua**: vibração total, pico ou amplitude dominante a mais de 6 desvios
  robustos (mediana e MAD, com piso de 3% da mediana).

O alarme diz qual medida se afastou e quanto ("vibração total: 1,3 vezes o normal").

**As duas bases:**

1. **Base adaptativa.** Aprende 2 minutos no lugar onde está (pulando os 15 s da
   partida) e reaprende a cada minuto com os últimos 10 minutos de janelas sem
   alarme. Mudança lenta (aquecimento, clima) entra no normal; mudança rápida vira
   alarme. Janelas em alarme, os 30 s seguintes e os últimos 30 s antes de cada
   atualização não são aprendidos.
2. **Referência da instalação.** A base dos 2 primeiros minutos fica guardada e
   nunca muda. O painel mostra "vs. início": quanto o normal atual já se afastou
   dela. É o que revela um desgaste lento que a base adaptativa absorveria.

Se os alarmes cobrem 80% das janelas por 3 minutos, o detector pede investigação e
não aprende a mudança.

**Resultados** (`./.venv/bin/python analysis/avaliar_duas_bases.py`, saída em
`results/avaliacao_duas_bases.txt`):

| Teste | Base adaptativa | Base congelada |
|---|---|---|
| Alarme falso nas 3 sessões normais (3169 janelas) | 0% | 5,7% |
| Falha brusca simulada (+30% por 60 s, 12 injeções) | 12 de 12, 99,8% das janelas | |
| Subida lenta de 1,5%/min | 4,5% das janelas em alarme, "vs. início" +20% | 44% |
| Subida lenta de 2%/min | 63% em alarme, investigação após 11,8 min | 57% |

As falhas são simuladas por software sobre gravações normais reais. Isso está dito
no artigo e no painel.

## Como usar

Dentro de `predictive-maintenance/`, uma vez só:

```
python3 -m venv .venv
.venv/bin/pip install -r analysis/requirements.txt
```

Grave o `aquisicao_esp32` na placa (com o `credenciais.h` criado) e feche o monitor
serial da Arduino IDE. Depois, os atalhos:

| Atalho | O que faz |
|---|---|
| `./apresentar` | Painel completo do detector de duas bases, ao vivo. Tecla `M` mostra a nota do modelo |
| `./apresentar reserva` | Toca a sessão 3 com uma falha simulada aos 3 min, se a placa falhar na hora |
| `./gravar` | Pergunta o nome da gravação (o lugar do cooler, ou Enter para teste) e grava em `data/` com gráfico ao vivo |
| `./grafico` | Só o gráfico da vibração, com a corrente no canto |

A primeira versão, com o modelo treinado uma vez, não tem atalho. Ela roda direto
de `analysis/legacy/`, por exemplo
`.venv/bin/python analysis/legacy/treino.py data/rep*.csv --descarte 300`.

Os vídeos da apresentação não ficam no repositório, porque são pesados. Eles são
gerados localmente em `results/`: `video_brusca.mp4`, `video_lenta.mp4` e
`video_completo.mp4` por `analysis/videos_duas_bases.py`, e `ciclo_adaptativo.mp4`
por `analysis/video_ciclo.py`.

O passo a passo da montagem e das gravações está em [`docs/montagem.md`](docs/montagem.md).

## Customizações

O que foi desenvolvido além do uso padrão das bibliotecas e da IDE:

- **Leitura direta do ADXL345.** O firmware configura os registradores e usa o FIFO
  em modo stream, sem biblioteca.
- **FFT na placa.** Implementação própria da FFT radix-2, com janela de Hann e
  correção do ganho da janela, para a amplitude sair em g. Conferida com senos de
  amplitude e frequência conhecidas.
- **Taxa estimada por janela.** A conversão para Hz usa a duração medida pelo ESP32
  (417 Hz na bancada, não os 400 nominais).
- **Hora por NTP em vez de relógio externo.** O módulo DS1302 foi descartado depois
  de medido: contava seis vezes mais rápido que o tempo real.
- **Avisos de falha de sensor.** Linhas `# ALARME` quando o ADXL345 ou o INA219 param
  de responder; o INA219 é religado a cada 2 s.
- **Tacômetro por interrupção**, com debounce de 4 ms, que baixou a leitura de
  ~15 mil para ~3,6 mil rpm. Ainda conta a mais.
- **Corrente pela média da janela.** O motor sem escovas puxa corrente em pulsos, e
  uma leitura solta varia mais de 80 mA sem falha nenhuma.
- **Medidas totais invariantes à orientação.** O ventilador solto mudava a divisão da
  vibração entre os eixos sem mudar o total; o detector passou a usar só totais.
- **Detector de duas bases.** Linha de base adaptativa com as proteções contra
  aprender a falha, referência fixa da instalação e pedido de investigação. O
  Isolation Forest padrão do scikit-learn foi combinado com a régua robusta porque a
  nota dele satura longe do normal, e ganhou as regras de duas janelas e 3 desvios
  depois de alarmes falsos nos testes ao vivo.
- **Painel completo** com reconexão automática da serial, registro de eventos e modo
  de reprodução com falha simulada.
- **Atalhos** (`./gravar`, `./apresentar` etc.) para gravar e apresentar sem digitar
  comandos longos.

## Limitações

- Ensaios em bancada, com um único ventilador. Ventilador de bancada não é compressor.
- As falhas da avaliação são simuladas por software; as físicas só aparecem nos testes
  ao vivo, sem números.
- As gravações cobrem minutos, não dias. A deriva ainda não vira alarme, porque separar
  clima de desgaste exige dias de dados e o contexto de operação (corrente, rotação,
  temperatura ambiente).
- A 400 Hz com I²C a 100 kHz, e sem contagem de estouros do FIFO, ainda não dá para
  afirmar que as 512 amostras de uma janela são contínuas.
- O tacômetro conta a mais; a rotação sai do espectro de vibração.
- O MQTT não foi implementado; a coleta depende da USB e do computador.

## Organização da pasta

| Pasta | Conteúdo |
|---|---|
| `firmware/` | Sketch principal do ESP32; os testes da bancada em `tests/` |
| `analysis/` | Detector, painel, gravação, avaliação e figuras; a primeira versão em `legacy/` |
| `data/` | As três sessões normais gravadas |
| `results/` | Avaliação, figuras e vídeos gerados (os vídeos não vão para o Git) |
| `assets/` | Imagens usadas no README e no artigo |
| `paper/` | Artigo (`.tex`), tradução de apoio e `refs.bib` |
| `docs/` | Montagem, decisões, roteiro da apresentação e documentos do processo |
| `docs/course/` | Materiais da disciplina: lista de compras, retirada de materiais, seminário 1 |

## Documentos

| Arquivo | Conteúdo |
|---|---|
| `paper/predictive-maintenance.tex` | Artigo, em inglês, no modelo do SBrT |
| `paper/predictive-maintenance-pt.md` | Tradução de apoio do artigo |
| `paper/refs.bib` | Referências do artigo e a entrada do repositório |
| `docs/montagem.md` | Montagem da bancada e roteiro dos ensaios |
| `docs/roteiro-apresentacao.md` | Roteiro da apresentação da AP1 |
| `docs/decisoes-do-projeto.md` | Decisões tomadas, com o porquê, e o que está em aberto |
| `docs/plano-do-prototipo.md` | Plano e lista de materiais |
| `docs/requirements.md`, `docs/specifications.md` | Requisitos e especificação |
| `docs/duvidas-professor.md` | Perguntas levadas ao professor e as respostas |
| `docs/guia-geral.md` | Checklist das atividades da disciplina |
| `docs/research-notes.md`, `docs/reference-contributions.md` | Notas sobre as referências e a contribuição de cada uma |

O `.tex` usa os caminhos do projeto no Overleaf (`assets/` e `results/` na mesma
pasta do arquivo). Para compilar a partir do repositório, copie essas duas pastas
para dentro de `paper/` ou ajuste os caminhos.
