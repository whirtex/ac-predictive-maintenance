# Bench assembly

Assembly order, one step at a time. Each step confirms itself before the next
one: if something fails, you know exactly what you touched last.

The pins mentioned are the ones in `firmware/esp32_acquisition/`.

## Before you start

| Must be ready | How to confirm |
|---|---|
| ESP32 uploading over USB | the IDE uploads without errors |
| INA219 with header pins and terminal block soldered | the board does not print `# INA219 absent` (address `0x40`) |
| ADXL345 with header pins soldered | the board prints `# ADXL345 responding` (address `0x53`) |

These messages come from the acquisition firmware, on the serial port at 115200.
If the INA219 is connected after the board starts, the firmware retries every
2 seconds and prints `# INA219 responding` when it finds it.

Tools: wire cutters, a small screwdriver and tape.

Use one of the cheap fans in the first steps. The test fan only goes in once
everything works.

## Safety rule: the order of connecting the INA219

The INA219 must **never** receive the 12 V (`VIN+` and `VIN−`) without its own
`VCC` and `GND` connected. With no power and no ground, the 12 V current finds
a path through the chip and leaves through `SDA` and `SCL` to pins 21 and 22 of
the ESP32. On 23 September 2026, with the `VCC` and `GND` of the INA219 loose
during a bench move, the ESP32 got hot and disappeared from USB. It came back
after cooling down, with everything off.

When assembling or touching anything: supply unplugged; first the `VCC` and
`GND` of the INA219, then `SDA` and `SCL`, then `VIN+` and `VIN−`, and only then
the supply into the outlet. When taking it apart, do the reverse, starting by
unplugging the supply.

## Step 1: the fan spins

Cut the small three-wire connector of the fan, the one with the yellow wire.
Set the large Molex aside, wrapped in tape.

Strip about 5 mm of the **red** and the **black**. The yellow stays insulated.

On the female P4 adapter: red to `+`, black to `−`. Plug the supply into the
outlet.

**Confirmed when:** the fan spins.

If it does not spin, swap red and black. That is almost always the cause, and
the fan survives the reversed test without burning.

## Step 2: the current is measured

Now the red wire no longer goes straight to the supply and passes through the
INA219.

| From | To |
|---|---|
| adapter `+` | INA219 `VIN+` (loose wire, tighten the screw) |
| INA219 `VIN−` | red of the fan |
| black of the fan | ground rail on the breadboard |
| adapter `−` | same ground rail |
| ESP32 `GND` | same ground rail |

And the data side of the INA219, with four jumpers: `VCC` to 3.3 V, `GND` to
GND, `SDA` to pin 21, `SCL` to pin 22.

The three grounds must meet on the same rail. Without that the sensor does not
read.

**Confirmed when:** the fan keeps spinning and the `current_ma` column shows a
value (about 150 mA with the fan on).

## Step 3: the speed is read

Strip the yellow wire and push it into a free row of the breadboard.

In the same row, put one leg of a **10 kΩ** resistor. The other leg goes to the
3.3 V rail.

Still in the yellow wire's row, a jumper to **pin 18** of the ESP32.

The resistor goes to **3.3 V**, never to 12 V. On 12 V it burns the ESP32.

**Confirmed when:** the firmware shows a speed around 3000 on the test fan.

## Step 4: the vibration

The ADXL345 has 8 pins, and the 6 that matter go like this:

| ADXL345 pin | Goes to |
|---|---|
| `SDA` | the breadboard SDA row, which goes to GPIO **21** of the ESP32 |
| `SCL` | the breadboard SCL row, which goes to GPIO **22** of the ESP32 |
| `VCC` | the `+` rail of the breadboard |
| `CS` | the same `+` rail, together with `VCC`: it turns on I2C mode |
| `GND` | the `−` rail of the breadboard |
| `SDO` | the same `−` rail, together with `GND`: it fixes the address at `0x53` |

`INT1` and `INT2` stay unconnected.

**The trap that cost the most time on the bench:** the `+`/`−` rails of the
breadboard are isolated from the rest. They only become real 3.3 V and GND if
there is an explicit jumper from the `3V3` pin of the ESP32 to the `+` rail,
and from the `GND` of the ESP32 to the `−` rail. Without those two jumpers the
sensor gets no power at all, and nothing finds `0x53`, with no hint that this
is the problem.

The ADXL345 shares the bus with the INA219. An ESP32 pin only takes one jumper,
so the wires meet on the breadboard. The holes connected inside are the ones
with the **same number**, from `a` to `e` or from `f` to `j`; holes in the same
letter and different numbers (30j and 31j) do not touch. In one free number go
the ADXL345 `SDA`, the INA219 `SDA` and a jumper to GPIO 21, each in its own
letter; in another number, the same with the two `SCL` and GPIO 22. If the
ESP32 is plugged into the breadboard, just use free holes of the column of pin
21 and of the column of pin 22. The `VCC` of both goes to the same `+` rail.

**Confirmed when:** the board prints `# ADXL345 responding` and the
`current_ma` column still shows a value.

Only after confirming does it go onto the fan. Gluing it first means finding a
defect with the board already stuck.

Where to glue: on the **side** of the fan, the smooth strip that runs around it,
near a corner. Not on the face of the blades.

The pin header sticks **out past the edge**, hanging in the air. If it ends up
between the board and the fan, the board rises on four stilts and starts to
swing on its own.

Tape the wires to the board about 3 cm from the sensor, always in the same
position. A loose wire swings, and the swing enters the measurement as if it
were machine vibration.

## Step 4b: the room climate

The DHT11 reads the air temperature and humidity of the room. They enter the
model as an operating condition, not as a fault signal, so the bench works
without it: the two climate columns just come out empty.

With the 4-pin DHT11, grille facing you, the pins from left to right are `+`,
data, not connected and `−`:

| DHT11 pin | Goes to |
|---|---|
| `+` | 3.3 V of the ESP32 |
| data | GPIO **13** of the ESP32 |
| `−` | GND of the ESP32 |

A 4.7 kΩ or 10 kΩ resistor goes between `+` and data. A 3-pin DHT11 module
already has it on the board.

**Confirmed when:** the last two columns of each line carry the temperature and
the humidity, and the board does not print `# DHT11 not responding`.

## Step 5: mounting on the board

The fan stands **upright**, glued to the wooden board with super glue. Screwing
it on upright turned out too hard, which is why the loose-mounting fault left
the project (see `design-decisions.md`).

Before gluing, check that the air inlet and outlet stay free. If the edge
resting on the board covers the blades, the normal condition is born partly
obstructed, and obstruction is exactly one of the faults to be measured.

Wait for the glue to cure before the first recording. The glue joint is made
once: it is not redone between one recording and the next.

## Recording, once everything is assembled

Upload `firmware/esp32_acquisition/` to the board and close the Arduino IDE
serial monitor. The first time, set up Python: `python3 -m venv .venv` and then
`.venv/bin/pip install -r analysis/requirements.txt`. On Windows, double-click
`install.bat` instead.

The shortcuts run in the repository root (on the Mac, `./name`; on Windows,
`name.bat`):

```
./record    records a session to data/<name>.csv and opens the live chart
./train     trains the detector on the healthy recordings you choose
./check     runs a recording through the trained detector and plots the alarms
./plot      live chart only: vibration, current, speed and climate
./present   the adaptive detector panel of the first stage (AP1)
```

To set up a unit, record it working well, right after maintenance, for a few
hours and in the climates it will face, then train on those recordings:

1. Turn the fan on.
2. Run `./record` and answer with the recording name, for example the place
   (`bench-night`). Enter alone records a test, `data/test-HHMMSS.csv`.
   `./record` never writes over a recording that already exists.
3. Let it record. The chart opens by itself, and the terminal shows the time.
4. Press `Ctrl+C`. The chart closes with it.
5. Run `./train`, choose the healthy recordings and wait for `model.pkl`.

From then on, record the unit as before and run `./check` on each new
recording: it says how much of it was out of the normal and which measure
weighed most. The first 5 minutes of every recording are the motor warming up
and raise no alarm. If the climate of a recording is new to the model, `./check`
says so: record a few healthy minutes in that climate and train again.

The faults of the article were made on purpose, one at a time, with the fan on
its board: a piece of tape firmly on one blade (unbalance), the same tape
loosely glued so that it flapped (loose part), and a wooden block 2 to 5 cm in
front of the outlet (obstruction).
