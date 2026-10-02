"""Records a fan session in the simplest way possible.

Use it through the ./record shortcut, in the repository root. It:

  1. finds the board's port by itself;
  2. asks for the name of the recording, which is the place where the fan
     sits (for example table-a, table-b or floor), or Enter for a test;
  3. records to data/<name>.csv (or data/test-HHMMSS.csv) and refuses to
     overwrite a file that already exists;
  4. opens the vibration and current chart in a separate window;
  5. shows the elapsed time and warns at 10 minutes.

Ctrl+C stops the recording and closes the chart.
"""

import glob
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime

import serial

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUGGESTED_DURATION_S = 10 * 60


def find_port():
    ports = sorted(glob.glob("/dev/cu.usbserial*") + glob.glob("/dev/cu.SLAB*")
                   + glob.glob("/dev/cu.wchusbserial*"))
    if not ports:
        print("The board was not found. Check the USB cable and try again.")
        sys.exit(1)
    return ports[0]


def choose_file():
    answer = input("Recording name, the place of the fan (e.g. table-a, floor), "
                   "or just Enter for a test: ").strip()
    if answer == "":
        return os.path.join(ROOT, "data", f"test-{datetime.now():%H%M%S}.csv")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", answer):
        print("Use only letters, numbers, - and _ in the name.")
        sys.exit(1)
    path = os.path.join(ROOT, "data", f"{answer}.csv")
    if os.path.exists(path):
        print(f"A recording with that name already exists (data/{answer}.csv).")
        print("Choose another name, or delete that file first.")
        sys.exit(1)
    return path


def main():
    port_path = find_port()
    path = choose_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    relative = os.path.relpath(path, ROOT)

    port = serial.Serial(port_path, 115200, timeout=1)
    port.reset_input_buffer()
    port.readline()   # the first line may arrive cut off

    # The chart runs in its own process: if it hangs or is closed, the
    # recording goes on.
    chart = subprocess.Popen(
        [sys.executable, os.path.join(ROOT, "analysis", "monitor.py"), "--follow", path],
        start_new_session=True)

    print(f"\nRecording to {relative}. Ctrl+C to stop.\n")

    start = time.monotonic()
    windows = 0
    warned = False
    warned_silence = False
    with open(path, "a", encoding="utf-8") as out:
        try:
            while True:
                raw = port.readline()
                if not raw:
                    if (windows == 0 and not warned_silence
                            and time.monotonic() - start > 30):
                        warned_silence = True
                        print("  The board sent nothing in 30 s. Press the EN button on the ESP32"
                              " and wait about 20 s; if nothing changes, stop with Ctrl+C.")
                    continue
                text = raw.decode(errors="replace").rstrip("\r\n")
                out.write(text + "\n")
                out.flush()

                if text.startswith("#"):
                    if "ALARM" in text:
                        print(text)
                    continue

                windows += 1
                elapsed = time.monotonic() - start
                minutes, seconds = divmod(int(elapsed), 60)
                print(f"\r  {minutes:02d}:{seconds:02d}   {windows} windows", end="", flush=True)
                if elapsed >= SUGGESTED_DURATION_S and not warned:
                    warned = True
                    print("\a\n  10 minutes! You can stop with Ctrl+C.")
        except KeyboardInterrupt:
            pass

    chart.send_signal(signal.SIGTERM)
    if windows == 0:
        # An empty file must not hold the name of the recording.
        os.remove(path)
        print("\n\nNothing was recorded, and the empty file was deleted. Check the board and"
              " run ./record again.")
        return
    print(f"\n\nDone: {windows} windows in {relative}.")
    print("To record in another place, move the fan and run ./record again.")


if __name__ == "__main__":
    main()
