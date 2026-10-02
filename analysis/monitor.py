"""Simple board monitor: the vibration on a chart and the current in the corner.

It compares nothing, has no reference line and gives no warnings. It only
shows what esp32_acquisition is measuring right now. Use it through the
./plot shortcut.

With --follow, instead of reading the board, it follows the file that ./record
is writing. That is how ./record shows the chart.

The board can only be read by one program at a time: close the Arduino IDE
serial monitor, and do not run this together with ./record, which already
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

from csv_format import COLUMNS

WINDOW_S = 120

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
SERIES = "#2a78d6"

data = deque()          # (t, vibration, current)
lock = threading.Lock()


def num(v, digits):
    return f"{v:.{digits}f}"


def find_port():
    ports = sorted(glob.glob("/dev/cu.usbserial*") + glob.glob("/dev/cu.SLAB*")
                   + glob.glob("/dev/cu.wchusbserial*"))
    if not ports:
        print("The board was not found. Check the USB cable.")
        sys.exit(1)
    return ports[0]


def parse(line):
    """Returns (vibration, current) from one esp32_acquisition line."""
    fields = line.split(",")
    if len(fields) != len(COLUMNS) or fields[0] == "datetime":
        return None
    values = dict(zip(COLUMNS, fields))
    try:
        vibration = math.sqrt(sum(float(values[a + "_rms"]) ** 2 for a in "xyz"))
        current = float(values["current_ma"]) if values["current_ma"] else None
    except ValueError:
        return None
    return vibration, current


def read_board(path):
    import serial
    port = serial.Serial(path, 115200, timeout=1)
    port.readline()   # the first line may arrive cut off
    while True:
        line = port.readline().decode(errors="replace").strip()
        reading = parse(line)
        if reading:
            add(time.monotonic(), *reading)


def follow(path):
    """Follows a CSV being recorded: what already exists goes in at once, with
    the time rebuilt from the window duration, and the rest comes in live."""
    import os
    while not os.path.exists(path):
        time.sleep(0.5)
    with open(path, encoding="utf-8") as f:
        old = [l.strip() for l in f.read().splitlines()]
        readings = [r for r in map(parse, old) if r]
        now = time.monotonic()
        for i, reading in enumerate(readings):
            add(now - (len(readings) - 1 - i) * 1.23, *reading)
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
                add(time.monotonic(), *reading)


def add(t, vibration, current):
    with lock:
        data.append((t, vibration, current))
        while data and data[0][0] < t - WINDOW_S:
            data.popleft()


def build_window(clock=time.monotonic):
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
        "axes.edgecolor": GRID, "axes.labelcolor": INK_2,
        "xtick.color": INK_2, "ytick.color": INK_2, "font.size": 11,
        "axes.spines.top": False, "axes.spines.right": False,
    })
    fig, ax = plt.subplots(figsize=(10, 5.5))
    try:
        fig.canvas.manager.set_window_title("Vibration and current")
    except AttributeError:
        pass
    fig.subplots_adjust(top=0.78)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_xlim(-WINDOW_S, 0)
    ax.set_xlabel("seconds ago")
    ax.set_ylabel("total vibration (g)")
    line, = ax.plot([], [], color=SERIES, linewidth=2)

    vib_text = fig.text(0.125, 0.9, "", fontsize=22, fontweight="bold", color=INK)
    vib_label = fig.text(0.125, 0.85, "vibration now", fontsize=11, color=INK_2)
    cur_text = fig.text(0.9, 0.9, "", fontsize=22, fontweight="bold", color=INK, ha="right")
    cur_label = fig.text(0.9, 0.85, "current now", fontsize=11, color=INK_2, ha="right")
    _ = (vib_label, cur_label)

    def update(_):
        now = clock()
        with lock:
            copy = list(data)
        if not copy:
            vib_text.set_text("waiting for the board...")
            cur_text.set_text("")
            return []
        ts = [d[0] - now for d in copy]
        vs = [d[1] for d in copy]
        line.set_data(ts, vs)
        ax.set_ylim(0, max(vs) * 1.3)
        _, vibration, current = copy[-1]
        vib_text.set_text(f"{num(vibration, 3)} g")
        cur_text.set_text(f"{num(current, 0)} mA" if current is not None else "no INA219")
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
