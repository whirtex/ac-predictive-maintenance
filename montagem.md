# Montagem da bancada

Ordem de montagem, um passo por vez. Cada passo se confirma sozinho antes do
seguinte: se alguma coisa falhar, você sabe exatamente o que mexeu por último.

Os pinos citados são os do `firmware/aquisicao_esp32/`.

## Antes de começar

| Precisa estar pronto | Como confirmar |
|---|---|
| ESP32 gravando pelo cabo USB | a IDE grava sem erro |
| INA219 com barra de pinos e borneira soldadas | scanner mostra `0x40` |
| ADXL345 com barra de pinos soldada | scanner mostra `0x53` |

Ferramentas: alicate de corte, chave de fenda pequena e fita.

Use uma das ventoinhas baratas nos primeiros passos. O cooler de ensaio só entra
quando tudo já estiver funcionando.

## Passo 1 — o ventilador gira

Corte o conector pequeno de três fios do ventilador, o que tem o amarelo. O Molex
grande fica de lado, enrolado com fita.

Descasque uns 5 mm do **vermelho** e do **preto**. O amarelo continua isolado.

No adaptador P4 fêmea: vermelho no `+`, preto no `−`. Espete a fonte na tomada.

**Confirma quando:** o ventilador gira.

Se não girar, inverta vermelho e preto. É a causa quase sempre, e o ventilador
aguenta o teste invertido sem queimar.

## Passo 2 — a corrente é medida

Agora o vermelho deixa de ir direto na fonte e passa por dentro do INA219.

| De | Para |
|---|---|
| `+` do adaptador | `VIN+` do INA219 (fio solto, aperta o parafuso) |
| `VIN−` do INA219 | vermelho do ventilador |
| preto do ventilador | linha do negativo, na protoboard |
| `−` do adaptador | mesma linha do negativo |
| `GND` do ESP32 | mesma linha do negativo |

E o lado dos dados do INA219, com quatro jumpers: `VCC` nos 3,3 V, `GND` no GND,
`SDA` no pino 21, `SCL` no pino 22.

Os três negativos precisam se encontrar na mesma linha. Sem isso o sensor não lê.

**Confirma quando:** o ventilador continua girando e o scanner acha `0x40`.

## Passo 3 — a rotação é lida

Descasque o fio amarelo e espete ele numa linha livre da protoboard.

Na mesma linha, ponha uma perna de um resistor de **10 kΩ**. A outra perna vai na
linha dos 3,3 V.

Ainda na mesma linha do amarelo, um jumper até o **pino 18** do ESP32.

O resistor vai nos **3,3 V**, nunca nos 12 V. Nos 12 V ele queima o ESP32.

**Confirma quando:** o firmware mostra rotação por volta de 3000 no cooler de ensaio.

## Passo 4 — a vibração

O ADXL345 tem 8 pinos, e os 6 que importam vão assim:

| Pino do ADXL345 | Vai para |
|---|---|
| `SDA` | direto no GPIO **21** do ESP32 (sem passar pela protoboard) |
| `SCL` | direto no GPIO **22** do ESP32 (sem passar pela protoboard) |
| `VCC` | fileira do `+` da protoboard |
| `CS` | mesma fileira do `+`, junto com o `VCC` — liga o modo I2C |
| `GND` | fileira do `−` da protoboard |
| `SDO` | mesma fileira do `−`, junto com o `GND` — fixa o endereço em `0x53` |

`INT1` e `INT2` ficam sem ligar.

**A armadilha que mais custou tempo na bancada:** as fileiras `+`/`−` da
protoboard são isoladas do resto. Elas só viram 3,3 V e GND de verdade se
existir um jumper explícito do pino `3V3` do ESP32 até a fileira `+`, e do
`GND` do ESP32 até a fileira `−`. Sem esses dois jumpers, o sensor fica sem
alimentação nenhuma, e nenhum scanner acha `0x53` — sem dar nenhuma pista de
que o problema é esse.

O ADXL345 divide o barramento com o INA219: mesmos `SDA` e `SCL`, e mesma
fileira `+` para o `VCC`.

**Confirma quando:** o scanner acha `0x40` e `0x53` juntos.

Só depois de confirmar é que ele vai para o ventilador. Colar antes significa
descobrir defeito com a placa já grudada.

Onde cola: na **lateral** do cooler, aquela faixa lisa que dá a volta nele, perto de
um canto. Não é na face da hélice.

A barra de pinos fica **para fora da borda**, pendurada no vazio. Se ela ficar entre
a placa e o cooler, a placa sobe em quatro palafitas e passa a balançar sozinha.

Prenda os fios com fita na tábua, a uns 3 cm do sensor, e sempre na mesma posição.
Fio solto balança e o balanço entra na medição como se fosse vibração da máquina.

## Passo 5 — montagem na tábua

O ventilador fica **em pé**, colado na tábua com super cola. Aparafusar em pé se
mostrou difícil demais, e por isso a falha de fixação frouxa saiu do projeto (ver
`decisoes-do-projeto.md`).

Antes de colar, confira que a entrada e a saída de ar ficam livres. Se a borda
apoiada na tábua tapar a hélice, a condição normal já nasce meio obstruída, e a
obstrução é justamente uma das falhas medidas.

Espere a cola curar antes do primeiro ensaio. A colagem é única: ela não é refeita
entre uma repetição e outra.

## Gravação dos ensaios, depois de tudo montado

Os dados de treino saem do `firmware/aquisicao_esp32/`, gravados no computador
pelo `analysis/captura_serial.py`. O script ocupa a porta serial, então o monitor
do Arduino IDE fica fechado durante a gravação.

1. Prepare o Python uma vez, dentro de `predictive-maintenance/`:
   `python3 -m venv .venv`, depois `source .venv/bin/activate` e
   `pip install -r analysis/requirements.txt`. Nas próximas vezes, basta o
   `source .venv/bin/activate`.
2. Grave o `aquisicao_esp32` na placa e feche o monitor serial.
3. Rode `python analysis/captura_serial.py /dev/cu.usbserial-XXXX data/ensaio.csv`.
4. A placa reinicia quando o script abre a porta, e os rótulos voltam para
   `normal` e repetição 1. Digite no terminal a condição e a repetição de
   verdade: `c normal` e `r 1`.
5. A cada troca de condição, digite a nova: `c obstrucao`, `c desbalanceamento`,
   `c atrito`. Sem isso os dados não servem para nada.

Condições: normal, obstrução, desbalanceamento e, se o mecanismo ficar pronto,
atrito. Dez minutos cada, descartando os três primeiros. Três repetições por
condição, desfazendo e refazendo a falha a cada repetição.

Depois de gravar: `python analysis/treino.py data/*.csv`. As repetições 1 e 2
treinam, a 3 avalia.
