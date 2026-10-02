# Predictive maintenance for air-conditioning equipment

Prototype for the course IBM3119, Embedded Systems Project (Ibmec, 2026).

This project was developed in a repository shared with another project of the
course, and it was moved here with its commit history filtered. The commits
before the English translation have the files and comments in Portuguese. The
translation is in the commits that follow.

The goal is an embedded system that monitors the condition of air-conditioning
equipment in continuous operation, such as units in server rooms, hospitals and
telecom shelters, and detects deviations that can guide maintenance. Vibration
is the main signal and the only input of the detector, on the professor's
guidance. Current and speed are recorded as support. The first version detects
anomalies. It does not say which fault it is and does not estimate the
remaining useful life.

Development has two stages. **On the bench**, a 12 V fan makes it possible to
build the acquisition chain and cause controlled changes. **On the target
equipment**, installing the sensors on an air conditioner still depends on
access to the unit and on a proper electrical setup. The bench results do not
show performance on a real air conditioner.

How it works today: an ESP32 reads the ADXL345, the INA219 and the tachometer,
computes the features of each window of ~1.23 s and sends one CSV line over
USB. On the computer, an **adaptive two-baseline detector** learns what is
normal in place during the first 2 minutes, relearns every minute and keeps the
installation baseline to show drift. MQTT is left for the field installation
(the college network requires a web login, which the board cannot complete).

## Bench status

| Part | Status |
|---|---|
| Vibration (ADXL345) | Working; the continuity of the samples inside the window has not been measured yet |
| Current (INA219) | Working, window average (148 to 153 mA across the sessions) |
| Speed (tachometer) | Reads, but counts 25% to 52% too many; the reliable speed comes from the vibration peak (~46.4 Hz, ~2780 rpm) |
| Features on the ESP32 | Working; the FFT was checked against known sine waves |
| Recording, panel and adaptive detector | Working live on the bench |
| Data | Three independent normal sessions in `data/` (12.3, 21.5 and 37.1 min) |
| Faults | Simulated in software over the normal sessions; physical disturbances only in the live tests. Recordings of imbalance, friction and obstruction are left for the next stage |

## Bench hardware

| Component | Role |
|---|---|
| ESP32-WROVER-DEV | Microcontroller, with Wi-Fi for the time over NTP |
| ADXL345 (GY-291 board) | 3-axis accelerometer, glued to the side of the fan |
| INA219 | Fan current, in series with the supply |
| 12 V fan, 80 × 80 × 25 mm, 3 wires | Test equipment; the yellow wire is the tachometer |
| Regulated 12 V, 1 A supply, and P4 adapter with terminal | Fan power |
| 10 kΩ resistor | Tachometer pull-up |
| Breadboard, jumpers and a wooden board | Assembly; the fan is glued upright to the board |

### Bench wiring

| From | To |
|---|---|
| ADXL345 `SDA` / `SCL` | GPIO 21 / GPIO 22 |
| ADXL345 `VCC` and `CS` | 3.3 V (`CS` at 3.3 V turns on I2C mode) |
| ADXL345 `GND` and `SDO` | GND (`SDO` at GND fixes the address `0x53`) |
| INA219 `SDA` / `SCL` / `VCC` / `GND` | GPIO 21 / GPIO 22 / 3.3 V / GND |
| supply `+` → INA219 `VIN+` → `VIN−` → red of the fan | Path of the measured current |
| Yellow of the fan | GPIO 18, with 10 kΩ to 3.3 V |
| ESP32 GND, black of the fan and supply `−` | Same point |

The `+` and `−` rails of the breadboard only receive 3.3 V and GND if there is
a jumper from the `3V3` and the `GND` of the ESP32 to them. The full
step-by-step, with the check for each stage, is in
[`docs/assembly.md`](docs/assembly.md).

## Software

Board: ESP32 Wrover Module, `esp32` core 3.3.11 (it also compiles with 3.3.12),
Arduino IDE 2.3.10. External library: Adafruit INA219 1.2.3. The ADXL345 is
read directly over I²C. The `esp32_acquisition` sketch needs a local
`credentials.h` file; copy
[`credentials.h.example`](firmware/esp32_acquisition/credentials.h.example),
fill in the network name and password, and keep `credentials.h` out of Git.
Wi-Fi only synchronizes the clock over NTP; without a connection, the CSV uses
`boot+...` timestamps.

On the computer: Python 3 with `numpy`, `pandas`, `scikit-learn`, `matplotlib`
and `pyserial` (list in `analysis/requirements.txt`).

| Firmware (`firmware/`) | What it does |
|---|---|
| `esp32_acquisition` | Extracts features and emits one CSV line per window on the serial port |

| Analysis (`analysis/`) | What it does |
|---|---|
| `adaptive.py` | The two-baseline detector (Isolation Forest + ruler, adaptive baseline, installation reference) |
| `adaptive_panel.py` | Presentation panel, live or playing a recording |
| `record.py` | Records a session from the board into `data/` and shows the chart during recording |
| `monitor.py` | Simple chart of the vibration, with the current in the corner |
| `evaluate_two_baselines.py` | Offline evaluation of the detector on the three sessions (the numbers of the article) |
| `architecture_figure.py` | Architecture diagram used in the article |
| `csv_format.py` | Columns of the board CSV and the 5 total measures |

### What the board computes

The firmware sets the ADXL345 to 400 Hz, with the FIFO in stream mode, and
forms windows of 512 samples (~1.23 s at the measured 417 Hz). For each axis it
computes the RMS (with the mean removed), the peak, the kurtosis and, with a
Hann window and a 512-point FFT, the dominant frequency and its amplitude.
Current (window average) and speed come out as extra columns. That makes 19
columns per line.

## Model: two-baseline detector

The detector uses **5 measures that do not depend on the orientation of the
sensor**: the vector sum of the RMS, of the peaks and of the dominant
amplitudes of the three axes, the mean kurtosis and the median dominant
frequency. Each window goes through two tests, and one is enough to raise an
alarm:

- **Isolation Forest** (150 trees, over the 5 standardized measures). The
  threshold is the 0.2% quantile of the normal scores. It only raises an alarm
  if it flags two windows in a row and some measure is at least 3 deviations
  from normal.
- **Ruler**: total vibration, peak or dominant amplitude more than 6 robust
  deviations away (median and MAD, with a floor of 3% of the median).

The alarm says which measure moved and by how much ("total vibration: 1.3 times
normal").

**The two baselines:**

1. **Adaptive baseline.** It learns for 2 minutes where it sits (skipping the
   15 s of start-up) and relearns every minute from the last 10 minutes of
   windows without an alarm. A slow change (warm-up, weather) enters the normal;
   a fast change becomes an alarm. Windows in alarm, the 30 s after them and the
   last 30 s before each update are not learned.
2. **Installation reference.** The baseline of the first 2 minutes is kept and
   never changes. The panel shows "vs. start": how far the current normal has
   moved from it. It is what reveals a slow wear that the adaptive baseline
   would absorb.

If the alarms cover 80% of the windows for 3 minutes, the detector asks for an
inspection and does not learn the change.

**What the detector learns and what is fixed.** The code has no fixed vibration
value. On each machine, the detector learns by itself the normal (the median
and the deviation of each measure), the Isolation Forest threshold, the band of
the ruler and the installation reference. The parameters below, on the other
hand, are fixed in `adaptive.py` and were tuned for the bench fan:

| Parameter | Value |
|---|---|
| Ruler | 6 deviations |
| Deviations for the model to raise an alarm | 3, on some measure, in two windows in a row |
| Floor of the deviation | 3% of the median |
| Start-up skipped in the first learning | 15 s |
| Initial learning | 2 min |
| Relearning | every 60 s, from the last 10 min |
| Block after an alarm | 30 s |
| Inspection request | 80% of windows in alarm for 3 min |

These values hold for the bench. They have not been shown on other air
conditioners, and there is no general value yet. The likely way forward is to
work with percentages that fit any machine, but that is not decided.

**Results** (`./.venv/bin/python analysis/evaluate_two_baselines.py`, output in
`results/two_baseline_evaluation.txt`):

| Test | Adaptive baseline | Frozen baseline |
|---|---|---|
| False alarms on the 3 normal sessions (3169 windows) | 0% | 5.7% |
| Simulated sudden fault (+30% for 60 s, 12 injections) | 12 of 12, 99.8% of the windows | |
| Slow rise of 1.5%/min | 4.5% of the windows in alarm, "vs. start" +20% | 44% |
| Slow rise of 2%/min | 63% in alarm, inspection after 11.8 min | 57% |

The faults are simulated in software over real normal recordings. The article
and the panel say so.

## How to use

In the repository root, once:

```
python3 -m venv .venv
.venv/bin/pip install -r analysis/requirements.txt
```

Upload `esp32_acquisition` to the board (with `credentials.h` created) and
close the Arduino IDE serial monitor. Then the shortcuts:

| Shortcut | What it does |
|---|---|
| `./present` | Full panel of the two-baseline detector, live. The `M` key shows the model score |
| `./present backup` | Plays session 3 with a simulated fault at 3 min, in case the board fails on the spot |
| `./record` | Asks for the recording name (the place of the fan, or Enter for a test) and records into `data/` with a live chart |
| `./plot` | Only the vibration chart, with the current in the corner |

The step-by-step of the assembly and of the recordings is in
[`docs/assembly.md`](docs/assembly.md).

## Customizations

What was developed beyond the standard use of the libraries and the IDE:

- **Direct reading of the ADXL345.** The firmware sets the registers and uses
  the FIFO in stream mode, without a library.
- **FFT on the board.** Own radix-2 implementation, with a Hann window and
  correction of the window gain, so the amplitude comes out in g. Checked with
  sine waves of known amplitude and frequency.
- **Rate estimated per window.** The conversion to Hz uses the duration
  measured by the ESP32 (417 Hz on the bench, not the nominal 400).
- **Time over NTP instead of an external clock.** The DS1302 module was
  dropped after measuring it: it ran six times faster than real time.
- **Sensor failure warnings.** `# ALARM` lines when the ADXL345 or the INA219
  stop responding; the INA219 is restarted every 2 s.
- **Tachometer by interrupt**, with a 4 ms debounce, which lowered the reading
  from ~15 thousand to ~3.6 thousand rpm. It still counts too many.
- **Current as the window average.** The brushless motor draws current in
  pulses, and a single reading varies by more than 80 mA with no fault at all.
- **Total measures independent of the orientation.** The loose fan changed the
  split of the vibration between the axes without changing the total; the
  detector now uses only totals.
- **Two-baseline detector.** Adaptive baseline with protections against
  learning the fault, a fixed installation reference and an inspection request.
  The standard scikit-learn Isolation Forest was combined with the robust ruler
  because its score saturates far from normal, and it got the two-window and
  3-deviation rules after false alarms in the live tests.
- **Full panel** with automatic serial reconnection, an event log and a replay
  mode with a simulated fault.
- **Shortcuts** (`./record`, `./present` and so on) to record and present
  without typing long commands.

## Limitations

- Bench tests, with a single fan. A bench fan is not a compressor.
- The faults in the evaluation are simulated in software; the physical ones only
  show up in the live tests, with no numbers.
- The fixed parameters of the detector (table in "Model") were tuned for the
  bench fan and have not been tested on other machines.
- The recordings cover minutes, not days. Drift does not become an alarm yet,
  because separating weather from wear takes days of data and the operating
  context (current, speed, ambient temperature).
- At 400 Hz with I²C at 100 kHz, and with no count of FIFO overruns, it is not
  yet possible to say that the 512 samples of a window are continuous.
- The tachometer counts too many; the speed comes from the vibration spectrum.
- MQTT was not implemented; collection depends on USB and the computer.

## Repository layout

| Folder | Contents |
|---|---|
| `firmware/` | ESP32 acquisition sketch |
| `analysis/` | Detector, panel, recording, evaluation and figure |
| `data/` | The three normal recorded sessions |
| `results/` | Evaluation report and figure |
| `assets/` | Images used in the article |
| `paper/` | Article (`.tex`) and `refs.bib` |
| `docs/` | Bench assembly and design decisions |

## Documents

| File | Contents |
|---|---|
| `paper/predictive-maintenance.tex` | Article, in English, in the SBrT template |
| `paper/refs.bib` | References of the article and the repository entry |
| `docs/assembly.md` | Bench assembly and the recording routine |
| `docs/design-decisions.md` | Decisions taken, with the reason, and what was dropped |

The `.tex` uses the paths of the Overleaf project (`assets/` and `results/` in
the same folder as the file). To compile from the repository, copy those two
folders into `paper/` or adjust the paths.

## License

MIT, see [`LICENSE`](LICENSE).
