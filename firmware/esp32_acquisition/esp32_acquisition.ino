/*
  Acquisition chain on the ESP32-WROVER-DEV, to record the sessions that
  feed the detector.

  Vibration is the main signal of the project. For every window of 512
  samples (about 1.3 s at 400 Hz) the board computes, for each axis of the
  ADXL345, the time and frequency features, and emits one CSV line. Current
  and speed come as support columns: if the INA219 or the tachometer are not
  connected, the column comes out empty or zero and the recording goes on.

  The temperature left the project on 22 September 2026, on the professor's
  guidance. The temporary DHT11 left with it.

  Wiring (see docs/assembly.md, Step 4, for the wiring that works):
    ADXL345 and INA219 -> GPIO 21 SDA, GPIO 22 SCL
    Fan tachometer     -> GPIO 18   (with a 10 kOhm resistor to 3.3 V)

  The tachometer gives TWO pulses per turn, the standard for a PC fan.

  Lines that start with # are comments and alarms: pandas ignores them with
  comment='#'.

  Needs the Adafruit INA219 library.
*/

#include <WiFi.h>
#include <time.h>
#include <Wire.h>
#include <Adafruit_INA219.h>

// The network name and password live in credentials.h, which is not in the
// repository. Copy credentials.h.example as credentials.h and fill it in
// before uploading.
#include "credentials.h"

// It sits here at the top because the Arduino build generates the function
// prototypes before the rest of the code, and processAxis() returns this type.
struct Features {
  float rms, peak, kurtosis, domFreq, domAmp;
};

// Brasilia time, no daylight saving
const long  TIMEZONE_SECONDS = -3 * 3600;
const char* NTP_SERVER       = "pool.ntp.org";

// --- ADXL345 ---------------------------------------------------------

#define ADXL_ADDRESS 0x53

#define REG_DEVID     0x00
#define REG_BW_RATE   0x2C
#define REG_POWER_CTL 0x2D
#define REG_DATA_FMT  0x31
#define REG_DATAX0    0x32
#define REG_FIFO_CTL  0x38
#define REG_FIFO_STAT 0x39

// Full resolution: 3.9 mg per step in any range.
const float G_PER_STEP = 1.0 / 256.0;

// 100 kHz and 400 Hz: the combination already proven on the bench.
const uint32_t I2C_CLOCK = 100000;
const uint8_t  RATE_REG  = 0x0C;   // 400 Hz

// A power of 2, as the FFT requires. 512 samples at 400 Hz give windows of
// ~1.3 s and a resolution of ~0.8 Hz.
#define N_SAMPLES 512

// Below this the FFT sees slow drift, not the motor.
const float MIN_FREQ_HZ = 3.0;

// --- INA219 and tachometer -------------------------------------------

#define INA_ADDRESS 0x40
#define TACH_PIN 18
#define PULSES_PER_REV 2

const unsigned long INA_INTERVAL_MS = 20;

Adafruit_INA219 ina219;

volatile unsigned long pulses = 0;
volatile unsigned long lastPulseUs = 0;

// Pulses closer together than this are motor noise, not turns (4 ms allows
// up to 7500 RPM). Without the filter, the bench counted 15 to 20 thousand
// RPM; with it, ~3800 RPM, against the ~2780 RPM that the dominant
// frequency of the vibration shows. The reading still counts too many and
// the detector does not use it: the reliable speed comes from
// x_domfreq x 60. Counting only drops of at least 1 ms was tried and
// zeroed the reading, so the real shape of the pulse has to be seen on an
// oscilloscope before the next adjustment.
const unsigned long MIN_INTERVAL_US = 4000;

void IRAM_ATTR countPulse() {
  unsigned long now = micros();
  if (now - lastPulseUs < MIN_INTERVAL_US) return;
  lastPulseUs = now;
  pulses++;
}

// --- state -----------------------------------------------------------

bool timeValid = false;
bool adxlOk = false;
bool inaOk  = false;

float samples[3][N_SAMPLES];
int   nSamples = 0;
unsigned long windowStart = 0;

// FFT buffers, reused axis by axis
float re[N_SAMPLES];
float im[N_SAMPLES];

double currentSum = 0;
int    nCurrent = 0;
unsigned long lastCurrent = 0;

// --- I2C -------------------------------------------------------------

bool writeReg(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(ADXL_ADDRESS);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool readReg(uint8_t reg, uint8_t* dest, uint8_t count) {
  Wire.beginTransmission(ADXL_ADDRESS);
  Wire.write(reg);
  if (Wire.endTransmission() != 0) return false;
  if (Wire.requestFrom((uint8_t)ADXL_ADDRESS, count) != count) return false;
  for (uint8_t i = 0; i < count; i++) dest[i] = Wire.read();
  return true;
}

bool startAdxl() {
  uint8_t id;
  if (!readReg(REG_DEVID, &id, 1) || id != 0xE5) return false;
  return writeReg(REG_BW_RATE, RATE_REG)
      && writeReg(REG_DATA_FMT, 0x0B)     // full resolution, 16 g range
      && writeReg(REG_FIFO_CTL, 0x00)     // empty the queue...
      && writeReg(REG_FIFO_CTL, 0x80)     // ...and turn on stream mode
      && writeReg(REG_POWER_CTL, 0x08);   // measuring
}

bool inaResponds() {
  Wire.beginTransmission(INA_ADDRESS);
  return Wire.endTransmission() == 0;
}

bool startIna() {
  if (!inaResponds() || !ina219.begin()) return false;
  ina219.setCalibration_16V_400mA();
  return true;
}

// --- Wi-Fi and time --------------------------------------------------

void connectWiFi() {
  Serial.print("# connecting to ");
  Serial.println(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long deadline = millis() + 15000;
  while (WiFi.status() != WL_CONNECTED && millis() < deadline) {
    delay(300);
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("# no Wi-Fi: the timestamp will count from boot");
    return;
  }

  configTime(TIMEZONE_SECONDS, 0, NTP_SERVER);

  struct tm now;
  if (getLocalTime(&now, 10000)) {
    timeValid = true;
    Serial.println("# time synced by NTP");
  } else {
    Serial.println("# NTP did not answer: the timestamp will count from boot");
  }
}

// With NTP, the real date and time. Without NTP, seconds since boot, with a
// boot+ prefix so they are not mistaken for real time inside the CSV.
void timestamp(char* dest, size_t size) {
  if (timeValid) {
    struct tm now;
    if (getLocalTime(&now, 100)) {
      strftime(dest, size, "%Y-%m-%d %H:%M:%S", &now);
      return;
    }
  }
  snprintf(dest, size, "boot+%lu", millis() / 1000);
}

// --- window processing -----------------------------------------------

// In-place radix-2 FFT, over re[] and im[].
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
  for (int size = 2; size <= n; size <<= 1) {
    float ang = -2.0 * PI / size;
    float wr = cos(ang), wi = sin(ang);
    for (int i = 0; i < n; i += size) {
      float cr = 1, ci = 0;
      for (int k = 0; k < size / 2; k++) {
        int a = i + k, b = i + k + size / 2;
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

// Computes the features of one axis. The window mean is removed before
// anything else: it is gravity, which is fixed and would hide the vibration.
Features processAxis(int axis, float rateHz) {
  const float* x = samples[axis];
  int n = N_SAMPLES;

  double sum = 0;
  for (int i = 0; i < n; i++) sum += x[i];
  float mean = sum / n;

  double m2 = 0, m4 = 0;
  float peak = 0;
  for (int i = 0; i < n; i++) {
    float d = x[i] - mean;
    double d2 = (double)d * d;
    m2 += d2;
    m4 += d2 * d2;
    if (fabs(d) > peak) peak = fabs(d);
  }
  m2 /= n;
  m4 /= n;

  Features c;
  c.rms      = sqrt(m2);
  c.peak     = peak;
  c.kurtosis = m2 > 0 ? m4 / (m2 * m2) : 0;

  // Hann window for the FFT, which reduces leakage between bins.
  for (int i = 0; i < n; i++) {
    float hann = 0.5 * (1 - cos(2 * PI * i / (n - 1)));
    re[i] = (x[i] - mean) * hann;
    im[i] = 0;
  }
  fft(n);

  // Amplitude in g: 2/N for the one-sided spectrum, and /0.5 for the gain
  // of the Hann window.
  int kMin = (int)ceil(MIN_FREQ_HZ * n / rateHz);
  if (kMin < 1) kMin = 1;
  float best = 0;
  int kBest = kMin;
  for (int k = kMin; k < n / 2; k++) {
    float mag = sqrt(re[k] * re[k] + im[k] * im[k]);
    if (mag > best) {
      best = mag;
      kBest = k;
    }
  }
  c.domFreq = kBest * rateHz / n;
  c.domAmp  = best * 4.0 / n;
  return c;
}

void emitWindow() {
  unsigned long durationMs = millis() - windowStart;
  // The real rate of the ADXL345 has a tolerance; measuring it is more
  // honest than assuming 400 Hz in the conversion to frequency.
  float rateHz = durationMs > 0 ? N_SAMPLES * 1000.0 / durationMs : 400.0;

  noInterrupts();
  unsigned long p = pulses;
  pulses = 0;
  interrupts();
  float rpm = durationMs > 0 ? (float)p / PULSES_PER_REV * 60000.0 / durationMs : 0;

  char datetime[32];
  timestamp(datetime, sizeof(datetime));

  Serial.print(datetime);
  Serial.print(",");
  Serial.print(rateHz, 1);

  for (int axis = 0; axis < 3; axis++) {
    Features c = processAxis(axis, rateHz);
    Serial.print(",");
    Serial.print(c.rms, 5);
    Serial.print(",");
    Serial.print(c.peak, 4);
    Serial.print(",");
    Serial.print(c.kurtosis, 3);
    Serial.print(",");
    Serial.print(c.domFreq, 1);
    Serial.print(",");
    Serial.print(c.domAmp, 5);
  }

  Serial.print(",");
  if (nCurrent > 0) Serial.print(currentSum / nCurrent, 1);
  Serial.print(",");
  Serial.println(rpm, 0);

  currentSum = 0;
  nCurrent = 0;
}

// --- main ------------------------------------------------------------

void setup() {
  Serial.begin(115200);
  delay(400);

  Wire.begin(21, 22);
  Wire.setClock(I2C_CLOCK);

  pinMode(TACH_PIN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(TACH_PIN), countPulse, FALLING);

  connectWiFi();

  inaOk = startIna();
  if (!inaOk) Serial.println("# INA219 absent: the current column comes out empty");

  Serial.println("datetime,rate_hz,"
                 "x_rms,x_peak,x_kurtosis,x_domfreq,x_domamp,"
                 "y_rms,y_peak,y_kurtosis,y_domfreq,y_domamp,"
                 "z_rms,z_peak,z_kurtosis,z_domfreq,z_domamp,"
                 "current_ma,rpm");
}

void loop() {
  static unsigned long lastAlarm = 0;

  if (!adxlOk) {
    if (!startAdxl()) {
      if (millis() - lastAlarm >= 1000) {
        lastAlarm = millis();
        Serial.println("# ALARM: ADXL345 not responding. Check SDA, SCL, VCC, GND, CS and SDO.");
      }
      delay(50);
      return;
    }
    adxlOk = true;
    nSamples = 0;
    Serial.println("# ADXL345 responding");
  }

  uint8_t status;
  if (!readReg(REG_FIFO_STAT, &status, 1)) {
    adxlOk = false;
    return;
  }

  uint8_t entries = status & 0x3F;
  for (uint8_t i = 0; i < entries; i++) {
    uint8_t b[6];
    if (!readReg(REG_DATAX0, b, 6)) {
      adxlOk = false;
      return;
    }
    if (nSamples == 0) {
      windowStart = millis();
      noInterrupts();
      pulses = 0;
      interrupts();
    }
    for (int k = 0; k < 3; k++) {
      int16_t raw = (int16_t)((b[2 * k + 1] << 8) | b[2 * k]);
      samples[k][nSamples] = raw * G_PER_STEP;
    }
    nSamples++;

    if (nSamples == N_SAMPLES) {
      emitWindow();
      nSamples = 0;
    }
  }

  // Current: window average, because a brushless motor draws in pulses.
  if (millis() - lastCurrent >= INA_INTERVAL_MS) {
    lastCurrent = millis();
    if (inaOk) {
      if (inaResponds()) {
        currentSum += ina219.getCurrent_mA();
        nCurrent++;
      } else {
        inaOk = false;
        Serial.println("# ALARM: INA219 stopped responding");
      }
    }
  }

  // Without the INA219, it tries again every 2 s, and the vibration
  // collection goes on in the meantime.
  static unsigned long lastInaAttempt = 0;
  if (!inaOk && millis() - lastInaAttempt >= 2000) {
    lastInaAttempt = millis();
    if (startIna()) {
      inaOk = true;
      Serial.println("# INA219 responding");
    }
  }

  delay(2);
}
