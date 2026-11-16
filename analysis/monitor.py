"""Simple board monitor: vibration, current, speed and room climate, live.

It compares nothing and has no reference line or warnings. It only shows
what esp32_acquisition is measuring now, in four charts of the last
WINDOW_S seconds. Use it through the ./plot shortcut.

With --follow, instead of reading the board, it follows the file that
./record is writing. That is how ./record shows its chart.

Only one program can read the board at a time: close the Arduino IDE
serial monitor and do not run it together with ./record, which already
opens its own chart.
"""

import glob
import math
import sys
import threading
import time
from collections import deque

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

from csv_format import CLIMATE, COLUMNS, valid_line

WINDOW_S = 600

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
BLUE = "#2a78d6"
ORANGE = "#e07b00"
PURPLE = "#7b3fb5"
RED = "#d62828"
TEAL = "#0f9b9b"

data = deque()           # (t, {"vib", "cur", "rpm", "temp", "hum"})
lock = threading.Lock()


def find_port():
    ports = sorted(glob.glob("/dev/cu.usbserial*") + glob.glob("/dev/cu.SLAB*")
                   + glob.glob("/dev/cu.wchusbserial*"))
    if not ports:
        print("The board was not found. Check the USB cable.")
        sys.exit(1)
    return ports[0]


def _number(text):
    try:
        return float(text) if text != "" else None
    except ValueError:
        return None


def parse(line):
    """Returns the measurements of an esp32_acquisition line, or None. Older
    recordings have no climate: temperature and humidity come out None."""
    fields = line.split(",")
    if not valid_line(fields):
        return None
    values = dict(zip(COLUMNS + CLIMATE, fields))
    try:
        vib = math.sqrt(sum(float(values[a + "_rms"]) ** 2 for a in "xyz"))
    except ValueError:
        return None
    return {"vib": vib, "cur": _number(values["current_ma"]),
            "rpm": _number(values["rpm"]),
            "temp": _number(values.get("air_temp_c", "")),
            "hum": _number(values.get("air_humidity_pct", ""))}


def read_board(path):
    import serial
    port = serial.Serial(path, 115200, timeout=1)
    port.readline()   # the first line may arrive cut off
    while True:
        line = port.readline().decode(errors="replace").strip()
        reading = parse(line)
        if reading:
            add(time.monotonic(), reading)


def follow(path):
    """Follows a CSV being recorded: what already exists comes in at once,
    with the time rebuilt from the window duration, and the rest comes in
    live."""
    import os
    while not os.path.exists(path):
        time.sleep(0.5)
    with open(path, encoding="utf-8") as f:
        old = [l.strip() for l in f.read().splitlines()]
        readings = [r for r in map(parse, old) if r]
        now = time.monotonic()
        for i, reading in enumerate(readings):
            add(now - (len(readings) - 1 - i) * 1.23, reading)
        chunk = ""
        while True:
            new = f.readline()
            if not new:
                time.sleep(0.2)
                continue
            chunk += new
            if not chunk.endswith("\n"):
                continue
            reading = parse(chunk.strip())
            chunk = ""
            if reading:
                add(time.monotonic(), reading)


def add(t, reading):
    with lock:
        data.append((t, reading))
        while data and data[0][0] < t - WINDOW_S:
            data.popleft()


def build_window(clock=time.monotonic):
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
        "axes.edgecolor": GRID, "axes.labelcolor": INK_2,
        "xtick.color": INK_2, "ytick.color": INK_2, "font.size": 10,
        "axes.spines.top": False,
    })
    fig, axes = plt.subplots(2, 2, figsize=(12, 7.5), sharex=True)
    try:
        fig.canvas.manager.set_window_title("Bench live")
    except AttributeError:
        pass
    fig.subplots_adjust(hspace=0.35, wspace=0.28, top=0.9, bottom=0.08)
    ax_vib, ax_cur, ax_rpm, ax_climate = axes.flat
    ax_hum = ax_climate.twinx()
    for ax in (ax_vib, ax_cur, ax_rpm, ax_climate):
        ax.spines["right"].set_visible(ax is ax_climate)
        ax.grid(True, color=GRID, linewidth=0.8)
        ax.set_xlim(-WINDOW_S / 60, 0)
    for ax in (ax_rpm, ax_climate):
        ax.set_xlabel("minutes ago")
    ax_vib.set_ylabel("g")
    ax_cur.set_ylabel("mA")
    ax_rpm.set_ylabel("RPM")
    ax_climate.set_ylabel("°C", color=RED)
    ax_hum.set_ylabel("%", color=TEAL)

    l_vib, = ax_vib.plot([], [], color=BLUE, linewidth=1.8)
    l_cur, = ax_cur.plot([], [], color=ORANGE, linewidth=1.8)
    l_rpm, = ax_rpm.plot([], [], color=PURPLE, linewidth=1.8)
    l_temp, = ax_climate.plot([], [], color=RED, linewidth=1.8)
    l_hum, = ax_hum.plot([], [], color=TEAL, linewidth=1.8)
    notice = fig.text(0.5, 0.955, "", fontsize=14, color=INK, ha="center")

    def series(copy, now, key):
        points = [((t - now) / 60, m[key]) for t, m in copy if m[key] is not None]
        return [p[0] for p in points], [p[1] for p in points]

    def span(ax, ys, slack, floor=None):
        if not ys:
            return
        low, high = min(ys), max(ys)
        margin = max((high - low) * 0.2, slack)
        ax.set_ylim(low - margin if floor is None else max(floor, low - margin), high + margin)

    def title(ax, name, value, text):
        ax.set_title(f"{name}: {text if value is not None else 'no reading'}",
                     loc="left", fontsize=13, fontweight="bold", color=INK)

    def update(_):
        now = clock()
        with lock:
            copy = list(data)
        if not copy:
            notice.set_text("waiting for the board...")
            return []
        notice.set_text("")
        last = copy[-1][1]
        for line, ax, key, slack, floor in (
                (l_vib, ax_vib, "vib", 0.01, 0), (l_cur, ax_cur, "cur", 5, 0),
                (l_rpm, ax_rpm, "rpm", 50, 0), (l_temp, ax_climate, "temp", 0.5, None),
                (l_hum, ax_hum, "hum", 2, 0)):
            xs, ys = series(copy, now, key)
            line.set_data(xs, ys)
            span(ax, ys, slack, floor)
        title(ax_vib, "Vibration", last["vib"], f"{last['vib']:.3f} g")
        title(ax_cur, "Current", last["cur"],
              f"{last['cur']:.0f} mA" if last["cur"] is not None else "")
        title(ax_rpm, "Speed", last["rpm"],
              f"{last['rpm']:.0f} RPM" if last["rpm"] is not None else "")
        if last["temp"] is not None and last["hum"] is not None:
            ax_climate.set_title(f"Climate: {last['temp']:.1f} °C, {last['hum']:.0f} %",
                                 loc="left", fontsize=13, fontweight="bold", color=INK)
        else:
            ax_climate.set_title("Climate: no reading", loc="left", fontsize=13,
                                 fontweight="bold", color=INK)
        return []

    return fig, update


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--follow":
        threading.Thread(target=follow, args=(sys.argv[2],), daemon=True).start()
    else:
        port = find_port()
        threading.Thread(target=read_board, args=(port,), daemon=True).start()
    fig, update = build_window()
    _animation = FuncAnimation(fig, update, interval=200, cache_frame_data=False)  # noqa: F841
    try:
        plt.show()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
