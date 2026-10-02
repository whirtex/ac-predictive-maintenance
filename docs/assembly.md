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
serial monitor. The rest is three shortcuts, run in the Terminal inside the
repository root:

```
./record    records a session and opens the vibration and current chart
./present   full panel of the adaptive detector, for the presentation
./plot      live chart only: vibration and current, with no recording or comparing
```

The first time, set up Python: `python3 -m venv .venv` and then
`.venv/bin/pip install -r analysis/requirements.txt`.

**For the first assessment (AP1), record only normal operation, in three
sessions.** In each one:

1. Turn the fan on.
2. Run `./record` and answer with the recording name. For the three evaluation
   sessions, use `rep1`, `rep2` and `rep3`; to record in another place, use its
   name (for example `table-b` or `floor`).
3. Let it record. The chart opens by itself, and the terminal shows the time and
   warns at 10 minutes.
4. Press `Ctrl+C`. The chart closes with it.
5. Turn the fan off for 1 minute before the next session.

Do not touch the assembly between sessions. For a test that does not go into
the evaluation, answer with just Enter instead of a name: the file becomes
`data/test-HHMMSS.csv`. `./record` does not write over a recording that already
exists; to redo one, delete its `data/<name>.csv` first.

After the three, the detector evaluation runs with
`.venv/bin/python analysis/evaluate_two_baselines.py`, and the numbers go to
`results/`.

At the presentation, run `./present`. The detector learns what is normal in
place during the first 2 minutes, with the fan on and untouched, and then
watches, relearning every minute. It does not matter which table it sits on or
whether the fan is cold: it learns right there. The panel shows the state, each
update of the normal, each alarm as a red dot, the current and the speed. The
`M` key shows the Isolation Forest score in an extra chart. If the board fails,
`./present backup` plays recorded session 3 with a simulated fault at 3
minutes, marked as simulated on screen.

If at least 80% of the readings stay in alert for 3 minutes, the panel asks the
team to investigate the equipment. The detector does not learn from readings in
alert and keeps the previous pattern. Gradual changes that it considers normal
keep being absorbed automatically; that is a limitation to evaluate in the slow
fault tests.

The chart updates every 1.23 s: covering the inlet shows up well, and shaking
the fan for 2 or 3 seconds shows up better than a quick tap. `Ctrl+C` in the
terminal, or closing the window, ends the panel.

Recording the faults (obstruction and imbalance) and measuring F1 is left for
after the AP1.
