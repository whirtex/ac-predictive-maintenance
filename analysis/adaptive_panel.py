"""Full panel of the adaptive detector. It is what ./present opens.

Connect the board anywhere: for the first 2 minutes the detector learns what
is normal there, and then it watches, relearning every minute. The panel shows
everything it does:

  - at the top, the state (learning, normal, peak, continuous anomaly) and a
    box with the time on, updates, alarms, current, speed and how far the
    normal has moved since the installation (drift);
  - in the top chart, the total vibration and the normal band, which change at
    every update, marked by a vertical line;
  - a red dot for each reading in alert, whether raised by the Isolation
    Forest or by the protection against strong changes; the M key shows the
    model score in an extra chart;
  - at the bottom, the log of every update and every alarm.

Usage:
    python analysis/adaptive_panel.py                      # live board
    python analysis/adaptive_panel.py --replay data/rep3.csv
    python analysis/adaptive_panel.py --replay data/rep3.csv --fault 300
        # injects 60 s of vibration 30% stronger at 300 s of the recording,
        # for rehearsing; the panel says the fault is simulated

Keys, with the panel window selected:
    M   shows or hides the model score chart (Isolation Forest).
    q   closes

Ctrl+C in the terminal, or closing the window, ends it.
"""

import argparse
import glob
import threading
import time
from collections import deque
from datetime import datetime

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

import adaptive as A
from csv_format import COLUMNS

WINDOW_S = 180          # how much of the past the charts show
SUSTAINED_S = 2.0       # outside the normal for longer than this: continuous anomaly
PERSISTENT_S = 60       # shows a warning before the 3-minute escalation
EPISODE_END_S = 3.0     # back to normal for this long: the episode is over
N_SAMPLES = 512

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
INK_3 = "#8a8984"
GRID = "#e4e3df"
BAND = "#e9e8e3"
SERIES = "#2a78d6"
ANOMALY = "#4a3aa7"
GOOD = "#0ca30c"
SERIOUS = "#ec835a"
CRITICAL = "#d03b3b"
NEUTRAL = "#8a8984"


def num(v, digits=3):
    return f"{v:.{digits}f}"


def duration(s):
    m, s = divmod(int(s), 60)
    return f"{m} min {s:02d} s" if m else f"{s} s"


class Panel:
    def __init__(self):
        self.detector = A.AdaptiveDetector()
        self.lock = threading.Lock()
        self.points = deque()        # (t, vibration, anomaly, outside, passed_limit)
        self.show_model = False      # M key: model score chart
        self.events = deque(maxlen=8)
        self.last = None             # result of the last window
        self.current = None
        self.speed = None
        self.simulating = False
        self.episode = None
        self.alarms = 0
        self.now = None
        self.updates_seen = 0
        self.connection = None       # connection warning, if the board dropped

    def clock_time(self, window):
        text = window.get("datetime", "")
        if text and not text.startswith("boot"):
            return text[-8:]
        return datetime.now().strftime("%H:%M:%S")

    def add(self, t, window, simulated=False):
        with self.lock:
            self.now = t
            self.simulating = simulated
            r = self.detector.add(t, window)
            self.last = r
            v = r["measures"]["rms_total"]
            passed = r.get("anomaly") is not None and r["anomaly"] > r["limit"]
            self.points.append((t, v, r.get("anomaly"), r.get("outside"), passed))
            while self.points and self.points[0][0] < t - WINDOW_S:
                self.points.popleft()
            current = window.get("current_ma")
            self.current = current if current == current else None
            self.speed = r["measures"]["domfreq"] * 60

            stamp = self.clock_time(window)
            new = self.detector.updates[self.updates_seen:]
            for a in new:
                if a["change"] is None:
                    text = (f"{stamp}   ● Learned what is normal here: vibration "
                            f"{num(a['rms_mean'])} g, from {a['windows']} measurements")
                else:
                    text = (f"{stamp}   ↻ Updated the normal: {num(a['rms_mean'])} g "
                            f"({a['change']:+.1f}%), from {a['windows']} measurements")
                self.events.appendleft(text)
            self.updates_seen = len(self.detector.updates)

            if r.get("new_escalation"):
                self.events.appendleft(
                    f"{stamp}   ■ Persistent anomaly for 3 min: call maintenance")
            if r["phase"] == "detecting":
                self._episode(t, r, stamp)

    def _episode(self, t, r, stamp):
        if r["outside"]:
            if self.episode is None:
                self.episode = {"start": t, "end": t, "worst": r, "stamp": stamp}
                self.alarms += 1
            ep = self.episode
            ep["end"] = t
            if r["anomaly"] > ep["worst"]["anomaly"]:
                ep["worst"] = r
        elif self.episode and t - self.episode["end"] >= EPISODE_END_S:
            ep = self.episode
            dur = ep["end"] - ep["start"] + N_SAMPLES / 400
            if dur > SUSTAINED_S:
                text = f"■ Continuous anomaly for {duration(dur)}"
            else:
                text = "▲ Peak"
            self.events.appendleft(f"{ep['stamp']}   {text}: {ep['worst']['detail']}")
            self.episode = None

    def persistent(self):
        """More than half of the last minute in alarm, even if choppy."""
        if self.now is None or self.detector.model is None:
            return False
        recent = [p[3] for p in self.points if p[0] >= self.now - PERSISTENT_S]
        return len(recent) >= 20 and sum(bool(f) for f in recent) > len(recent) / 2

    def state(self):
        r = self.last
        if r is None:
            return "WAITING FOR THE BOARD", "", NEUTRAL
        if r["phase"] == "learning":
            return ("●  LEARNING WHAT IS NORMAL HERE",
                    f"keep the fan on and do not touch it: {duration(r['remaining'])} left", NEUTRAL)
        if r.get("investigate"):
            return ("■  CALL MAINTENANCE",
                    f"anomaly for {duration(r['alert_time_s'])}: inspect the equipment", CRITICAL)
        if self.episode:
            ep = self.episode
            if ep["end"] - ep["start"] + N_SAMPLES / 400 > SUSTAINED_S:
                return "■  CONTINUOUS ABNORMAL VIBRATION", ep['worst']['detail'], CRITICAL
            return "▲  PEAK DETECTED", ep['worst']['detail'], SERIOUS
        return "●  NORMAL", "nothing outside the learned normal", GOOD


# positions [left, bottom, width, height] of the charts
POS_ONE = [0.08, 0.30, 0.64, 0.46]        # only the vibration chart
POS_TWO = [0.08, 0.50, 0.64, 0.26]        # vibration, with the model chart below
POS_MODEL = [0.08, 0.29, 0.64, 0.15]      # model score (M key)


def build_window(panel):
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
        "axes.edgecolor": GRID, "axes.labelcolor": INK_2,
        "xtick.color": INK_2, "ytick.color": INK_2, "font.size": 10,
        "axes.spines.top": False, "axes.spines.right": False,
    })
    fig = plt.figure(figsize=(13, 9))
    try:
        fig.canvas.manager.set_window_title("Adaptive vibration detector")
    except AttributeError:
        pass
    ax_top = fig.add_axes([0.06, 0.84, 0.66, 0.12])
    ax_info = fig.add_axes([0.76, 0.42, 0.23, 0.54])
    ax = fig.add_axes(POS_ONE)
    ax_an = fig.add_axes(POS_MODEL, sharex=ax)
    ax_log = fig.add_axes([0.06, 0.02, 0.92, 0.19])
    for a in (ax_top, ax_info, ax_log):
        a.axis("off")

    title = ax_top.text(0, 0.72, "", fontsize=22, fontweight="bold",
                        transform=ax_top.transAxes, va="center")
    detail = ax_top.text(0, 0.25, "", fontsize=12, color=INK_2,
                         transform=ax_top.transAxes, va="center")
    warning = ax_top.text(0, -0.15, "", fontsize=11, color=SERIOUS, fontweight="bold",
                          transform=ax_top.transAxes, va="center")
    info = ax_info.text(0.05, 0.98, "", fontsize=11, color=INK, va="top",
                        family="monospace", transform=ax_info.transAxes, linespacing=1.6)
    log = ax_log.text(0, 1.0, "", fontsize=10.5, color=INK, va="top",
                      family="monospace", transform=ax_log.transAxes)

    for a in (ax, ax_an):
        a.grid(True, color=GRID, linewidth=0.8)
    ax.set_xlim(-WINDOW_S, 0)
    ax.set_ylabel("total vibration (g)")
    from matplotlib.lines import Line2D
    marks = [
        Line2D([], [], marker="o", linestyle="none", color=CRITICAL, markersize=7,
               label="alert"),
        Line2D([], [], linestyle="none", label="M key: Isolation Forest"),
    ]
    ax.legend(handles=marks, loc="lower left", bbox_to_anchor=(0, 1.02), ncol=2,
              frameon=False, fontsize=9.5, labelcolor=INK_2, handletextpad=0.4,
              columnspacing=1.8, borderaxespad=0)
    ax_an.text(0, 1.04, "model score: above the limit, the combination of the 5 measures is odd",
               transform=ax_an.transAxes, fontsize=8.5, color=INK_2, va="bottom")

    def arrange():
        if panel.show_model:
            ax.set_position(POS_TWO)
            ax_an.set_visible(True)
            ax.tick_params(labelbottom=False)
            ax.set_xlabel("")
        else:
            ax.set_position(POS_ONE)
            ax_an.set_visible(False)
            ax.tick_params(labelbottom=True)
            ax.set_xlabel("seconds ago")
    arrange()
    ax_an.set_ylabel("anomaly\n(Isolation Forest)")
    ax_an.set_xlabel("seconds ago")

    line, = ax.plot([], [], color=SERIES, linewidth=2, zorder=3)
    alert_points, = ax.plot([], [], "o", color=CRITICAL, markersize=7, zorder=4)
    line_an, = ax_an.plot([], [], color=ANOMALY, linewidth=2, zorder=3)
    outside_an, = ax_an.plot([], [], "o", color=CRITICAL, markersize=6, zorder=4)
    extras = []

    def update(_):
        with panel.lock:
            now = panel.now
            points = list(panel.points)
            text, sub, color = panel.state()
            events = list(panel.events)
            updates = list(panel.detector.updates)
            det = panel.detector
            current, speed = panel.current, panel.speed
            vibration = panel.points[-1][1] if panel.points else None
            alarms, simulating = panel.alarms, panel.simulating
            drift = panel.last.get("drift") if panel.last else None

        title.set_text(text)
        title.set_color(color)
        detail.set_text(sub)
        if panel.connection:
            warning.set_text(panel.connection.upper())
        elif panel.persistent():
            warning.set_text("PERSISTENT ANOMALY: INSPECT THE EQUIPMENT")
        else:
            warning.set_text("SIMULATED FAULT: vibration raised by 30% in software" if simulating else "")
        log.set_text("Log\n" + ("\n".join(events) if events else "nothing yet"))

        on_for = (now - det.start) if (now is not None and det.start is not None) else 0
        since = (now - det.last_update) if det.last_update is not None else None
        info_lines = [
            f"on for         {duration(on_for)}",
            f"updates        {len(updates)}",
            f"last           {duration(since) + ' ago' if since is not None else '-'}",
            f"alarms         {alarms}",
            "",
            f"vibration      {num(vibration) + ' g' if vibration is not None else '-'}",
            f"current        {num(current, 0) + ' mA' if current is not None else '-'}",
            f"speed          {num(speed, 0) + ' RPM' if speed else '-'}",
            "",
        ]
        if updates:
            a = updates[-1]
            info_lines += [
                f"normal now     {num(a['rms_mean'])} g",
                f"vs. start      {f'{drift:+.1f}' if drift is not None else '0.0'}%",
            ]
        info.set_text("\n".join(info_lines))

        for artist in extras:
            artist.remove()
        extras.clear()
        if not points or now is None:
            return []

        ts = [p[0] - now for p in points]
        vs = [p[1] for p in points]
        line.set_data(ts, vs)
        alerts = [bool(p[3]) for p in points]
        alert_points.set_data([t for t, f in zip(ts, alerts) if f],
                              [v for v, f in zip(vs, alerts) if f])

        top = max(vs)
        # The normal band changes at every update.
        for i, a in enumerate(updates):
            lo_t = a["t"] - now
            hi_t = (updates[i + 1]["t"] - now) if i + 1 < len(updates) else 0
            if hi_t < -WINDOW_S:
                continue
            lo_t = max(lo_t, -WINDOW_S)
            low, high = a["rms_mean"] - 2 * a["rms_dev"], a["rms_mean"] + 2 * a["rms_dev"]
            extras.append(ax.fill_between([lo_t, hi_t], low, high, color=BAND, zorder=1, linewidth=0))
            extras.append(ax.plot([lo_t, hi_t], [a["rms_mean"]] * 2, color=INK_3, linewidth=1.5, zorder=2)[0])
            top = max(top, high)
            if a["t"] - now >= -WINDOW_S:
                x = a["t"] - now
                for axis in (ax, ax_an):
                    extras.append(axis.axvline(x, color=INK_3, linewidth=0.8, linestyle=":", zorder=1))
                label = "learned" if a["change"] is None else "updated"
                extras.append(ax.text(x, 1.0, " " + label, transform=ax.get_xaxis_transform(),
                                      fontsize=8, color=INK_3, va="top", ha="left"))
        if updates:
            a = updates[-1]
            extras.append(ax.text(-WINDOW_S + 1, a["rms_mean"] - 2 * a["rms_dev"],
                                  " normal band", color=INK_2, fontsize=9, va="top"))
        ax.set_ylim(0, top * 1.25)

        # In the model chart, red only where the model itself passed the limit.
        an = [(t, p[2], p[4]) for t, p in zip(ts, points) if p[2] is not None]
        if an:
            line_an.set_data([x[0] for x in an], [x[1] for x in an])
            outside_an.set_data([x[0] for x in an if x[2]], [x[1] for x in an if x[2]])
            values = [x[1] for x in an]
            limits = []
            for i, a in enumerate(updates):
                lo_t = max(a["t"] - now, -WINDOW_S)
                hi_t = (updates[i + 1]["t"] - now) if i + 1 < len(updates) else 0
                if hi_t < -WINDOW_S:
                    continue
                extras.append(ax_an.plot([lo_t, hi_t], [a["limit"]] * 2, color=CRITICAL,
                                         linewidth=1.2, linestyle="--")[0])
                limits.append(a["limit"])
            low = min(values + limits)
            high = max(values + limits)
            margin = (high - low) * 0.15 or 0.05
            ax_an.set_ylim(low - margin, high + margin)
            if limits:
                extras.append(ax_an.text(-WINDOW_S + 1, limits[-1], " model limit",
                                         color=CRITICAL, fontsize=9, va="bottom"))
        else:
            line_an.set_data([], [])
            outside_an.set_data([], [])
        return []

    def on_key(event):
        if event.key == "q":
            plt.close(fig)
        elif event.key in ("m", "M"):
            panel.show_model = not panel.show_model
            arrange()
            fig.canvas.draw_idle()

    fig.canvas.mpl_connect("key_press_event", on_key)
    return fig, update


# --- sources -------------------------------------------------------------

def window_from_line(line):
    fields = line.split(",")
    if len(fields) != len(COLUMNS) or fields[0] == "datetime":
        return None
    window = dict(zip(COLUMNS, fields))
    try:
        for c in COLUMNS[1:17]:
            window[c] = float(window[c])
        for c in ("current_ma", "rpm"):
            window[c] = float(window[c]) if window[c] else float("nan")
    except ValueError:
        return None
    return window


def simulate_fault(window, factor=1.3):
    window = dict(window)
    for a in "xyz":
        for k in ("rms", "peak", "domamp"):
            window[f"{a}_{k}"] = window[f"{a}_{k}"] * factor
    return window


def read_board(panel):
    """Reads the board and, if the connection drops, warns on screen and tries again."""
    import serial
    while True:
        ports = sorted(glob.glob("/dev/cu.usbserial*") + glob.glob("/dev/cu.SLAB*")
                       + glob.glob("/dev/cu.wchusbserial*"))
        if not ports:
            panel.connection = "board not found: check the USB cable"
            time.sleep(2)
            continue
        try:
            port = serial.Serial(ports[0], 115200, timeout=1)
            port.readline()
            panel.connection = None
            while True:
                window = window_from_line(port.readline().decode(errors="replace").strip())
                if window:
                    panel.add(time.monotonic(), window)
        except (serial.SerialException, OSError):
            panel.connection = ("the connection to the board dropped. Close the Arduino IDE "
                                "Serial Monitor; trying again...")
            time.sleep(2)


def replay(panel, path, speed, fault):
    lines = [l.strip() for l in open(path, encoding="utf-8") if not l.startswith("#")]
    t = 0.0
    for line in lines:
        window = window_from_line(line)
        if not window:
            continue
        step = N_SAMPLES / window["rate_hz"]
        t += step
        simulated = fault is not None and fault <= t < fault + 60
        if simulated:
            window = simulate_fault(window)
        panel.add(t, window, simulated)
        time.sleep(step / speed)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", metavar="CSV", help="plays a recording instead of the board")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--fault", type=float, metavar="SECONDS",
                    help="with --replay: injects 60 s of simulated fault at that moment")
    args = ap.parse_args()

    panel = Panel()
    if args.replay:
        target, extra = replay, (panel, args.replay, args.speed, args.fault)
    else:
        target, extra = read_board, (panel,)
    threading.Thread(target=target, args=extra, daemon=True).start()

    fig, update = build_window(panel)
    _animation = FuncAnimation(fig, update, interval=300, cache_frame_data=False)  # noqa: F841
    try:
        plt.show()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
