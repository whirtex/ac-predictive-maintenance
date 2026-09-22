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
| Dois DS18B20 com as perninhas abertas em leque | os três conectores encaixam sem se tocar |

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

## Passo 4 — a temperatura

Os dois DS18B20 dividem tudo: os mesmos três fios e o mesmo pino.

Monte três linhas na protoboard, uma de 3,3 V, uma de GND e uma de dados. Cada
sensor tem três perninhas, e cada perninha vai na linha correspondente.

Entre a linha de dados e a de 3,3 V, um resistor de **4,7 kΩ**. Um só, para os dois
sensores. Se não tiver, um 10 kΩ funciona em fiação curta.

Da linha de dados, um jumper até o **pino 5** do ESP32.

**Confirma quando:** as duas colunas de temperatura saem preenchidas no CSV, com
valores parecidos enquanto os dois estão na mesma sala.

## Passo 5 — a vibração

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

## Passo 6 — montagem na tábua

Um furo na tábua embaixo do ventilador, para o ar entrar. O ventilador fica deitado
soprando para cima, assentado direto na madeira.

Quatro parafusos M4 × 50 mm atravessam o ventilador e a tábua, com porca por baixo.
São de máquina, não auto-atarraxantes: eles são o mecanismo da falha de fixação
frouxa, e vão ser apertados e afrouxados dezenas de vezes.

O sensor de temperatura do motor cola no **centro fixo** do ventilador, aquele da
etiqueta, de onde saem os fios. Um pedacinho de fita por cima dele, para o ar que
passa não resfriar o sensor.

O segundo sensor de temperatura fica solto no ar da sala, longe do jato.

## Ordem dos ensaios, depois de tudo montado

Normal, desbalanceamento, fixação frouxa, obstrução e atrito. Dez minutos cada,
descartando os três primeiros. Três repetições por condição, refazendo a falha a
cada repetição.

A cada troca, digite a condição no monitor serial: `c desbalanceamento`. Sem isso
os dados não servem para classificar nada.
