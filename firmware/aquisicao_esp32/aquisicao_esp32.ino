/*
  Cadeia de aquisicao na ESP32-WROVER-DEV, para gravar as sessoes que
  alimentam o detector.

  A vibracao e o sinal principal do projeto. A cada janela de 512
  amostras (cerca de 1,3 s a 400 Hz) a placa calcula, para cada eixo
  do ADXL345, as caracteristicas no tempo e na frequencia, e emite
  uma linha CSV. Corrente e rotacao entram como colunas de apoio: se
  o INA219 ou o tacometro nao estiverem ligados, a coluna sai vazia
  ou zerada e a gravacao continua.

  A temperatura saiu do projeto em 22 de setembro de 2026, por
  orientacao do professor. O DHT11 provisorio saiu junto.

  Ligacao (ver docs/montagem.md, Passo 4, para a fiacao que funciona):
    ADXL345 e INA219 -> GPIO 21 SDA, GPIO 22 SCL
    Tacometro cooler -> GPIO 18   (com resistor de 10 kOhm para 3,3 V)

  O tacometro entrega DOIS pulsos por volta, padrao de cooler de PC.

  Linhas que comecam com # sao comentario e alarme: o pandas ignora
  com comment='#'. O script analysis/legacy/captura_serial.py grava tudo num
  arquivo.

  Precisa da biblioteca Adafruit INA219.
*/

#include <WiFi.h>
#include <time.h>
#include <Wire.h>
#include <Adafruit_INA219.h>

// A rede e a senha ficam em credenciais.h, que nao vai para o
// repositorio. Copie credenciais.h.exemplo como credenciais.h e
// preencha antes de gravar.
#include "credenciais.h"

// Fica aqui no topo porque o Arduino gera os prototipos das funcoes
// antes do resto do codigo, e processarEixo() devolve este tipo.
struct Caracteristicas {
  float rms, pico, curtose, fDom, aDom;
};

// fuso de Brasilia, sem horario de verao
const long  FUSO_SEGUNDOS = -3 * 3600;
const char* SERVIDOR_NTP  = "pool.ntp.org";

// --- ADXL345 ---------------------------------------------------------

#define ENDERECO_ADXL 0x53

#define REG_DEVID     0x00
#define REG_BW_RATE   0x2C
#define REG_POWER_CTL 0x2D
#define REG_DATA_FMT  0x31
#define REG_DATAX0    0x32
#define REG_FIFO_CTL  0x38
#define REG_FIFO_STAT 0x39

// Resolucao total: 3,9 mg por passo em qualquer faixa.
const float G_POR_PASSO = 1.0 / 256.0;

// 100 kHz e 400 Hz: a combinacao ja provada na bancada.
const uint32_t CLOCK_I2C = 100000;
const uint8_t  TAXA_REG  = 0x0C;   // 400 Hz

// Potencia de 2, exigencia da FFT. 512 amostras a 400 Hz dao janelas
// de ~1,3 s e resolucao de ~0,8 Hz.
#define N_AMOSTRAS 512

// Abaixo disso a FFT enxerga deriva lenta, nao o motor.
const float FREQ_MINIMA_HZ = 3.0;

// --- INA219 e tacometro ----------------------------------------------

#define ENDERECO_INA 0x40
#define PINO_TACOMETRO 18
#define PULSOS_POR_VOLTA 2

const unsigned long INTERVALO_INA_MS = 20;

Adafruit_INA219 ina219;

volatile unsigned long pulsos = 0;
volatile unsigned long ultimoPulsoUs = 0;

// Pulsos mais proximos que isso sao ruido do motor, nao voltas (4 ms
// aceita ate 7500 RPM). Sem filtro, a bancada contou de 15 a 20 mil
// RPM; com ele, ~3800 RPM, contra ~2780 RPM que a frequencia dominante
// da vibracao mostra. A leitura ainda conta a mais e nao e usada pelo
// modelo: a rotacao confiavel vem de x_fdom x 60. Contar so quedas de
// pelo menos 1 ms foi testado e zerou a leitura, entao o formato real
// do pulso precisa ser visto num osciloscopio antes do proximo ajuste.
const unsigned long INTERVALO_MINIMO_US = 4000;

void IRAM_ATTR contarPulso() {
  unsigned long agora = micros();
  if (agora - ultimoPulsoUs < INTERVALO_MINIMO_US) return;
  ultimoPulsoUs = agora;
  pulsos++;
}

// --- estado ----------------------------------------------------------

bool horaValida = false;
bool adxlOk = false;
bool inaOk  = false;

float amostras[3][N_AMOSTRAS];
int   nAmostras = 0;
unsigned long inicioJanela = 0;

// buffers da FFT, reaproveitados eixo a eixo
float re[N_AMOSTRAS];
float im[N_AMOSTRAS];

double somaCorrente = 0;
int    nCorrente = 0;
unsigned long ultimaCorrente = 0;

// --- I2C -------------------------------------------------------------

bool escrever(uint8_t reg, uint8_t valor) {
  Wire.beginTransmission(ENDERECO_ADXL);
  Wire.write(reg);
  Wire.write(valor);
  return Wire.endTransmission() == 0;
}

bool ler(uint8_t reg, uint8_t* destino, uint8_t quantos) {
  Wire.beginTransmission(ENDERECO_ADXL);
  Wire.write(reg);
  if (Wire.endTransmission() != 0) return false;
  if (Wire.requestFrom((uint8_t)ENDERECO_ADXL, quantos) != quantos) return false;
  for (uint8_t i = 0; i < quantos; i++) destino[i] = Wire.read();
  return true;
}

bool iniciarAdxl() {
  uint8_t id;
  if (!ler(REG_DEVID, &id, 1) || id != 0xE5) return false;
  return escrever(REG_BW_RATE, TAXA_REG)
      && escrever(REG_DATA_FMT, 0x0B)     // resolucao total, faixa de 16 g
      && escrever(REG_FIFO_CTL, 0x00)     // esvazia a fila...
      && escrever(REG_FIFO_CTL, 0x80)     // ...e liga o modo stream
      && escrever(REG_POWER_CTL, 0x08);   // medindo
}

bool inaResponde() {
  Wire.beginTransmission(ENDERECO_INA);
  return Wire.endTransmission() == 0;
}

bool iniciarIna() {
  if (!inaResponde() || !ina219.begin()) return false;
  ina219.setCalibration_16V_400mA();
  return true;
}

// --- Wi-Fi e hora ----------------------------------------------------

void conectarWiFi() {
  Serial.print("# conectando em ");
  Serial.println(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_SENHA);

  unsigned long limite = millis() + 15000;
  while (WiFi.status() != WL_CONNECTED && millis() < limite) {
    delay(300);
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("# sem Wi-Fi: o carimbo vai contar a partir do boot");
    return;
  }

  configTime(FUSO_SEGUNDOS, 0, SERVIDOR_NTP);

  struct tm agora;
  if (getLocalTime(&agora, 10000)) {
    horaValida = true;
    Serial.println("# hora sincronizada por NTP");
  } else {
    Serial.println("# NTP nao respondeu: o carimbo vai contar a partir do boot");
  }
}

// Com NTP, data e hora reais. Sem NTP, segundos desde o boot, com o
// prefixo boot+ para nao se passarem por hora real dentro do CSV.
void carimbo(char* destino, size_t tamanho) {
  if (horaValida) {
    struct tm agora;
    if (getLocalTime(&agora, 100)) {
      strftime(destino, tamanho, "%Y-%m-%d %H:%M:%S", &agora);
      return;
    }
  }
  snprintf(destino, tamanho, "boot+%lu", millis() / 1000);
}

// --- processamento da janela -----------------------------------------

// FFT radix-2 no proprio lugar, sobre re[] e im[].
void fft(int n) {
  for (int i = 1, j = 0; i < n; i++) {
    int bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) {
      float t = re[i]; re[i] = re[j]; re[j] = t;
      t = im[i]; im[i] = im[j]; im[j] = t;
    }
  }
  for (int tam = 2; tam <= n; tam <<= 1) {
    float ang = -2.0 * PI / tam;
    float wr = cos(ang), wi = sin(ang);
    for (int i = 0; i < n; i += tam) {
      float cr = 1, ci = 0;
      for (int k = 0; k < tam / 2; k++) {
        int a = i + k, b = i + k + tam / 2;
        float tr = re[b] * cr - im[b] * ci;
        float ti = re[b] * ci + im[b] * cr;
        re[b] = re[a] - tr;
        im[b] = im[a] - ti;
        re[a] += tr;
        im[a] += ti;
        float ncr = cr * wr - ci * wi;
        ci = cr * wi + ci * wr;
        cr = ncr;
      }
    }
  }
}

// Calcula as caracteristicas de um eixo. A media da janela sai antes
// de tudo: ela e a gravidade, que e fixa e taparia a vibracao.
Caracteristicas processarEixo(int eixo, float taxaHz) {
  const float* x = amostras[eixo];
  int n = N_AMOSTRAS;

  double soma = 0;
  for (int i = 0; i < n; i++) soma += x[i];
  float media = soma / n;

  double m2 = 0, m4 = 0;
  float pico = 0;
  for (int i = 0; i < n; i++) {
    float d = x[i] - media;
    double d2 = (double)d * d;
    m2 += d2;
    m4 += d2 * d2;
    if (fabs(d) > pico) pico = fabs(d);
  }
  m2 /= n;
  m4 /= n;

  Caracteristicas c;
  c.rms     = sqrt(m2);
  c.pico    = pico;
  c.curtose = m2 > 0 ? m4 / (m2 * m2) : 0;

  // Janela de Hann para a FFT, que reduz o vazamento entre faixas.
  for (int i = 0; i < n; i++) {
    float hann = 0.5 * (1 - cos(2 * PI * i / (n - 1)));
    re[i] = (x[i] - media) * hann;
    im[i] = 0;
  }
  fft(n);

  // Amplitude em g: 2/N pelo espectro de um lado, e /0,5 pelo ganho
  // da janela de Hann.
  int kMin = (int)ceil(FREQ_MINIMA_HZ * n / taxaHz);
  if (kMin < 1) kMin = 1;
  float melhor = 0;
  int kMelhor = kMin;
  for (int k = kMin; k < n / 2; k++) {
    float mag = sqrt(re[k] * re[k] + im[k] * im[k]);
    if (mag > melhor) {
      melhor = mag;
      kMelhor = k;
    }
  }
  c.fDom = kMelhor * taxaHz / n;
  c.aDom = melhor * 4.0 / n;
  return c;
}

void emitirJanela() {
  unsigned long duracaoMs = millis() - inicioJanela;
  // A taxa real do ADXL345 tem tolerancia; medir e mais honesto que
  // assumir 400 Hz na conversao para frequencia.
  float taxaHz = duracaoMs > 0 ? N_AMOSTRAS * 1000.0 / duracaoMs : 400.0;

  noInterrupts();
  unsigned long p = pulsos;
  pulsos = 0;
  interrupts();
  float rpm = duracaoMs > 0 ? (float)p / PULSOS_POR_VOLTA * 60000.0 / duracaoMs : 0;

  char data_hora[32];
  carimbo(data_hora, sizeof(data_hora));

  Serial.print(data_hora);
  Serial.print(",");
  Serial.print(taxaHz, 1);

  for (int eixo = 0; eixo < 3; eixo++) {
    Caracteristicas c = processarEixo(eixo, taxaHz);
    Serial.print(",");
    Serial.print(c.rms, 5);
    Serial.print(",");
    Serial.print(c.pico, 4);
    Serial.print(",");
    Serial.print(c.curtose, 3);
    Serial.print(",");
    Serial.print(c.fDom, 1);
    Serial.print(",");
    Serial.print(c.aDom, 5);
  }

  Serial.print(",");
  if (nCorrente > 0) Serial.print(somaCorrente / nCorrente, 1);
  Serial.print(",");
  Serial.println(rpm, 0);

  somaCorrente = 0;
  nCorrente = 0;
}

// --- principal -------------------------------------------------------

void setup() {
  Serial.begin(115200);
  delay(400);

  Wire.begin(21, 22);
  Wire.setClock(CLOCK_I2C);

  pinMode(PINO_TACOMETRO, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PINO_TACOMETRO), contarPulso, FALLING);

  conectarWiFi();

  inaOk = iniciarIna();
  if (!inaOk) Serial.println("# INA219 ausente: a coluna de corrente sai vazia");

  Serial.println("data_hora,taxa_hz,"
                 "x_rms,x_pico,x_curtose,x_fdom,x_adom,"
                 "y_rms,y_pico,y_curtose,y_fdom,y_adom,"
                 "z_rms,z_pico,z_curtose,z_fdom,z_adom,"
                 "corrente_ma,rpm");
}

void loop() {
  static unsigned long ultimoAlarme = 0;

  if (!adxlOk) {
    if (!iniciarAdxl()) {
      if (millis() - ultimoAlarme >= 1000) {
        ultimoAlarme = millis();
        Serial.println("# ALARME: ADXL345 nao responde. Confira SDA, SCL, VCC, GND, CS e SDO.");
      }
      delay(50);
      return;
    }
    adxlOk = true;
    nAmostras = 0;
    Serial.println("# ADXL345 respondendo");
  }

  uint8_t estado;
  if (!ler(REG_FIFO_STAT, &estado, 1)) {
    adxlOk = false;
    return;
  }

  uint8_t entradas = estado & 0x3F;
  for (uint8_t i = 0; i < entradas; i++) {
    uint8_t b[6];
    if (!ler(REG_DATAX0, b, 6)) {
      adxlOk = false;
      return;
    }
    if (nAmostras == 0) {
      inicioJanela = millis();
      noInterrupts();
      pulsos = 0;
      interrupts();
    }
    for (int k = 0; k < 3; k++) {
      int16_t bruto = (int16_t)((b[2 * k + 1] << 8) | b[2 * k]);
      amostras[k][nAmostras] = bruto * G_POR_PASSO;
    }
    nAmostras++;

    if (nAmostras == N_AMOSTRAS) {
      emitirJanela();
      nAmostras = 0;
    }
  }

  // Corrente: media da janela, porque motor sem escovas puxa em pulsos.
  if (millis() - ultimaCorrente >= INTERVALO_INA_MS) {
    ultimaCorrente = millis();
    if (inaOk) {
      if (inaResponde()) {
        somaCorrente += ina219.getCurrent_mA();
        nCorrente++;
      } else {
        inaOk = false;
        Serial.println("# ALARME: INA219 parou de responder");
      }
    }
  }

  // Sem o INA219, tenta de novo a cada 2 s, e a coleta de vibracao
  // segue enquanto isso.
  static unsigned long ultimaTentativaIna = 0;
  if (!inaOk && millis() - ultimaTentativaIna >= 2000) {
    ultimaTentativaIna = millis();
    if (iniciarIna()) {
      inaOk = true;
      Serial.println("# INA219 respondendo");
    }
  }

  delay(2);
}
