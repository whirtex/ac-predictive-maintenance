#!/bin/sh
# Shows the board's vibration on a chart, with the current in the corner, live.
# It records nothing and compares with no reference.
cd "$(dirname "$0")" && exec .venv/bin/python analysis/monitor.py
