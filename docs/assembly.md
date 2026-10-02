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

## Regra de segurança: a ordem de ligar o INA219

O INA219 **nunca** pode receber os 12 V (`VIN+` e `VIN−`) sem estar com o `VCC` e o
`GND` dele ligados. Sem alimentação e sem terra, a corrente dos 12 V acha caminho
por dentro do chip e sai pelo `SDA` e pelo `SCL` até os pinos 21 e 22 do ESP32.
Em 23 de setembro de 2026, com o `VCC` e o `GND` do INA219 soltos na mudança de
bancada, o ESP32 esquentou e sumiu do USB. Ele voltou depois de esfriar, com tudo
desligado.

Ao montar ou mexer: fonte fora da tomada; primeiro o `VCC` e o `GND` do INA219,
depois o `SDA` e o `SCL`, depois o `VIN+` e o `VIN−`, e só então a fonte na
tomada. Ao desmontar, na ordem inversa, começando por tirar a fonte da tomada.

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
| `SDA` | linha de SDA da protoboard, que vai ao GPIO **21** do ESP32 |
| `SCL` | linha de SCL da protoboard, que vai ao GPIO **22** do ESP32 |
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

O ADXL345 divide o barramento com o INA219. Um pino do ESP32 só aceita um jumper,
então os fios se encontram na protoboard. Os furos ligados por dentro são os de
**mesmo número**, de `a` a `e` ou de `f` a `j`; furos na mesma letra e em números
diferentes (30j e 31j) não se tocam. Num número livre ficam o `SDA` do ADXL345, o
`SDA` do INA219 e um jumper até o GPIO 21, cada um numa letra; noutro número, o
mesmo com os dois `SCL` e o GPIO 22. Se o ESP32 estiver espetado na protoboard, basta usar
furos livres da coluna do pino 21 e da coluna do pino 22. O `VCC` dos dois vai na
mesma fileira `+`.

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

Grave o `firmware/aquisicao_esp32/` na placa e feche o monitor serial do Arduino
IDE. O resto são três atalhos, rodados no Terminal dentro de
`predictive-maintenance/`:

```
./gravar        grava uma sessão e abre o gráfico da vibração e da corrente
./apresentar    painel completo do detector adaptativo, para a apresentação
./grafico       só o gráfico ao vivo: vibração e corrente, sem gravar nem comparar
```

Na primeira vez, prepare o Python: `python3 -m venv .venv` e depois
`.venv/bin/pip install -r analysis/requirements.txt`.

**Para a AP1, grave só a operação normal, em três sessões.** Em cada uma:

1. Ligue o ventilador.
2. Rode `./gravar` e responda o nome da gravação. Para as três sessões da avaliação,
   use `rep1`, `rep2` e `rep3`; para gravar em outro lugar, use o nome dele (por
   exemplo `mesa-b` ou `chao`).
3. Deixe gravar. O gráfico abre sozinho, e o terminal mostra o tempo e avisa quando
   der 10 minutos.
4. Aperte `Ctrl+C`. O gráfico fecha junto.
5. Desligue o ventilador por 1 minuto antes da sessão seguinte.

Não mexa na montagem entre as sessões. Para um teste que não entra na avaliação,
responda só Enter no lugar do nome: o arquivo vira `data/teste-HHMMSS.csv`. O
`./gravar` não grava por cima de uma gravação que já existe; para refazer uma,
apague o `data/<nome>.csv` dela antes.

Depois das três, a avaliação do detector roda com
`.venv/bin/python analysis/avaliar_duas_bases.py`, e os números vão para `results/`.

Na apresentação, rode `./apresentar`. O detector aprende o normal do lugar nos
primeiros 2 minutos, com o ventilador ligado e sem tocar, e depois vigia,
reaprendendo a cada minuto. Não importa a mesa nem se o ventilador está frio:
ele aprende ali. O painel mostra o estado, cada atualização do normal, cada
alarme com um ponto vermelho, a corrente e a rotação. A tecla `M` mostra a nota
do Isolation Forest em um gráfico adicional. Se a placa falhar, `./apresentar reserva` toca a sessão 3 gravada, com
uma falha simulada aos 3 minutos, marcada como simulada na tela.

Se pelo menos 80% das leituras permanecerem em alerta por 3 minutos, o painel
pede que a equipe investigue o equipamento. O detector não aprende com as
leituras em alerta e preserva o padrão anterior. Mudanças graduais que ele
considera normais continuam sendo incorporadas automaticamente; essa é uma
limitação a avaliar nos ensaios de falha lenta.

Para mostrar a detecção e a investigação em 30 segundos, use o vídeo
`results/ciclo_adaptativo.mp4`. Ele combina a gravação normal da sessão 3 com
uma anomalia e uma intervenção **simuladas**. Para gerá-lo novamente:

```sh
.venv/bin/python analysis/video_ciclo.py
```

O gráfico atualiza a cada 1,23 s: tapar a entrada aparece bem, e balançar o
ventilador por 2 ou 3 segundos aparece melhor que um toque rápido. `Ctrl+C` no
terminal, ou fechar a janela, encerra o painel.

Gravar as falhas (obstrução e desbalanceamento) e medir o F1 ficou para depois da
AP1.
