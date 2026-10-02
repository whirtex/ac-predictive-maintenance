# Design decisions

The main decisions of the predictive maintenance prototype, grouped by topic,
with the reason, what was dropped and the limit that has to be stated in the
article. The longest part is the detector, because it changed the most.

## Scope and goal

- **Scope.** Condition monitoring, data handling, fault detection and
  evaluation, following the stages described by Meitz et al. Degradation
  modelling, prognosis and remaining useful life are out. Remaining useful life
  needs data from operation until failure, with several units and months of
  records.
- **Goal of the first version.** Anomaly detection. Telling the faults apart
  is left for the next stage, once faults have been recorded.
- **Continuous 24-hour operation** as the application scope.
- **Bench first, real air conditioner second** (decision of 18 September 2026).
  The first version of the article is built entirely on the test fan. A test
  on a real unit is not cancelled: it depends on confirming that the
  installation is safe. **Limit to state:** until the second stage happens, the
  article reports bench results, not air-conditioner results.

## Test equipment

- **A 12 V fan, not a stepper motor.** A fan spins at thousands of rpm, takes an
  imbalance from a mass on a blade and warms up under load. The main argument
  is about scope: the fan of a condenser unit **is** a fan, an electric motor
  turning blades to move air through a coil. The article says the bench uses a
  fan of the same class, not a generic rotating part.
- **Three-pin model.** The third pin is a tachometer output, with two pulses per
  turn, which gives a fourth signal at no cost.
- **Unit bought: one Cooler Master A8025-30RB-3AN-F1** (19 September 2026), 80 ×
  80 × 25 mm, 12 V, 3000 rpm, 0.30 A, no LED. The choice put delivery time ahead
  of the bearing type, which the maker does not state anywhere. This weighs less
  than it seems: every planned fault is applied from the outside, so none of
  them depends on the bearing wearing out.
- **The fan is glued upright to the board** (22 September 2026). Screwing it on
  upright was too hard, so the loose-mounting fault left the project. Three
  faults remain: obstruction, imbalance and friction. None of them has been
  recorded yet. The glue joint must leave the air inlet and outlet free;
  otherwise the normal condition is born partly obstructed.

## Sensors and measurement

- **Vibration is the main signal; current and speed are support; temperature is
  out.** Guidance from the professor on 22 September 2026, replacing the group
  vote of 16 September that had fixed three signals with equal weight. The
  professor called vibration the "gold" of the project. Temperature left because
  the bench had nowhere to attach a probe near the motor, and the fan warms up
  little: the reading would have been almost decorative.
- **Two current sensors.** The INA219 on the bench, which is low voltage, and a
  non-invasive current transformer (SCT-013) on real equipment, which is mains.
  Connecting the INA219 to 220 V does not work and is dangerous.
- **ADXL345 over MPU6050**, for the sampling ceiling.
- **Accelerometer on the side of the fan, near a corner** (20 September 2026).
  The side is recessed in the middle, so a board glued there would sit on a thin
  wall that flexes by itself. The pin header sticks out past the edge: between
  the board and the fan it would act as four stilts, and the sensor would
  measure its own swing. The wires are taped to the base about 3 cm from the
  sensor, in the same position every time, because a loose wire swings and the
  swing enters the measurement as machine vibration.
- **The tachometer counts too many pulses.** Without a filter it read 15 to 20
  thousand rpm. With a 4 ms debounce it reads about 3800 rpm, still 37% above
  the ~2780 rpm that the dominant vibration frequency shows. Counting only drops
  of at least 1 ms zeroed the reading, which says the real pulse does not have
  the assumed shape; it has to be seen on an oscilloscope. Meanwhile the speed
  comes from the vibration (dominant frequency × 60), and the detector does not
  use the tachometer.
- **Obstruction does not show in the current.** Measured on 21 September 2026,
  on a 0.16 A fan, comparing the mean of a free window with a covered one:

  | Condition | Difference | In deviations |
  |---|---|---|
  | lying down, 20 s, hand, inlet | −7.5 mA (−5.0%) | 0.4 |
  | lying down, 60 s, object, outlet | −9.5 mA (−6.3%) | 0.5 |
  | upright, 60 s, book, outlet | −1.1 mA (−0.7%) | 0.06 |

  All three are below one deviation, inside the noise. When the current moves,
  it moves down, which fits a small fan with less air to push. The aerodynamic
  stall that raises the current belongs to large axial fans, not to an 80 mm
  one. Obstruction therefore has to be seen in other signals; it has already been
  measured in the vibration.

## Data and acquisition

- **Data goes over USB in the prototype; MQTT is for the field** (23 September
  2026). The college network lets a device in only after a login on a web page.
  The ESP32 connects to the Wi-Fi but stays blocked before that login, which it
  cannot complete: neither MQTT nor NTP get through. Imitating the login form in
  the firmware was dropped, because it breaks easily and would leave a personal
  password on the board. Asking IT to release the board's address is the right
  path, but it was not going to happen before the first assessment. The article
  says that MQTT, with a local buffer, is the architecture for the field.
- **The time comes from NTP; the DS1302 module is out.** Measured on 18 and 19
  September 2026: with `delay(3000)` in the loop, the clock advanced 18 seconds
  per cycle, exactly six times faster than real time. Without a battery it also
  went back to the compile time at every power-up. The defect is in the module,
  so it was not worth fixing. Without a connection, the timestamp of each line
  counts from boot (`boot+123`).
- **The CSV has no labels; each recording is named after the place**
  (1 October 2026). The first version wrote three label columns in each line
  (`unit`, `condition` and `repetition`), changed during the session with serial
  commands, to train on labelled data and split training from testing by
  repetition. The current detector learns the normal by itself and uses none of
  them: the condition was `normal` in every line, and the unit was always `A`.
  The columns left the firmware, the scripts and the three CSVs, which went from
  22 to 19 fields. `./record` now asks for the recording name and refuses to
  overwrite an existing file.

## Detector: from a model trained once to an adaptive one

**First version.** An Isolation Forest trained only on healthy operation, the
same setup that Kolok et al. use with an ESP32 and MEMS sensors, compared with a
fixed limit on the RMS. It was trained on sessions 1 and 2 and tested on
session 3.

**What failed.** On session 3, a normal recording, the Isolation Forest flagged
100% of the windows as anomalous, and the fixed limit flagged 0%. The three
sessions are the same fan in normal operation, and the normal moved between
them: the median total RMS was 0.150, 0.155 and 0.144 g. On the bench, the same
fan also vibrated about 0.15 g on one table and about 0.10 g on another, a bigger
difference than an obstruction would cause, and the warming motor changes the
vibration slowly over more than 20 minutes. A model trained once goes stale when
the place or the conditions change.

**What replaced it** (24 September 2026): the two-baseline detector.

- It learns what is normal for 2 minutes where it sits, and then relearns every
  minute from the last 10 minutes of windows without an alarm.
- Each window goes through two tests, and one is enough for an alarm: the
  Isolation Forest, and a robust ruler. The ruler exists because the forest
  score saturates far from normal: a vibration 30% higher once sat right at the
  threshold. Live, the forest alone flagged swings of 1.7 to 2.8 deviations,
  about the size of the noise, so it only counts when it flags two windows in a
  row with some measure at 3 deviations or more.
- The start-up of the motor, the first 15 s, stays out of the first learning:
  it left the ruler 51% above normal.
- The measures are totals over the three axes, because a loose fan changed the
  split of vibration between axes without changing the total.

**The risk of an adaptive detector** is getting used to a fault that grows
slowly. So windows in alarm and the 30 s after them are not learned, the last
30 s before each update stay out, and the baseline of the first 2 minutes is
kept as the installation reference. The panel shows "vs. start", the drift of the
current normal from it. If the alarms cover 80% of the windows for 3 minutes, the
detector asks for an inspection and does not learn the change.

**Result** (three sessions, faults simulated in software): 0% false alarms with
the adaptive baseline against 5.7% with a baseline frozen after 2 minutes (10.5%
on session 3); a sudden +30% fault detected 12 times out of 12; a slow rise of
1.5% per minute with 4.5% of the windows in alarm and "vs. start" at +20%,
against 44% with the frozen baseline.

**Limits to state.** The parameters (ruler of 6 deviations, 3 deviations for the
model, floor of 3%, 15 s of start-up, 2 minutes of learning, 10 minutes of
memory) were tuned for the bench fan and hold for it only. There is no general
value yet; the likely way forward is percentages that fit any machine, but that
is not decided. The detector has a blind spot for changes slower than about 1.5%
per minute, which only the drift shows. The recordings cover minutes, not days,
and the faults are simulated.

## Left out of this version

- **Recording faults and telling them apart** stay for after the first
  assessment. Without fault recordings the article reports no F1: the
  quantitative result is the false-alarm rate on normal data, and the detection
  of real disturbances is qualitative, seen live by shaking the fan or covering
  its inlet.
- **Remote alerts and relay shutdown** are listed as future work. With MQTT
  they would join later as subscribers of the same topic, without changing the
  firmware.
- **MQTT in the prototype.** The data goes over USB (see above).
