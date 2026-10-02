"""Format of the CSV line emitted by esp32_acquisition.

It lives in its own file so that the live monitor, the detector and the panel
share the same list without importing each other.
"""

COLUMNS = [
    "datetime", "rate_hz",
    "x_rms", "x_peak", "x_kurtosis", "x_domfreq", "x_domamp",
    "y_rms", "y_peak", "y_kurtosis", "y_domfreq", "y_domamp",
    "z_rms", "z_peak", "z_kurtosis", "z_domfreq", "z_domamp",
    "current_ma", "rpm",
]

VIBRATION = [c for c in COLUMNS if c[:2] in ("x_", "y_", "z_")]
SUPPORT = ["current_ma", "rpm"]

# Name of each feature in words, for the alarm messages.
NAMES = {"rms": "RMS", "peak": "peak", "kurtosis": "kurtosis",
         "domfreq": "dominant frequency", "domamp": "dominant-frequency amplitude"}


def readable_name(column):
    if column in TOTAL_NAMES:
        return TOTAL_NAMES[column]
    if column == "current_ma":
        return "current"
    if column == "rpm":
        return "speed"
    axis, kind = column.split("_", 1)
    return f"{NAMES.get(kind, kind)} on the {axis.upper()} axis"


# --- total measures ------------------------------------------------------
# They add the three axes into a single value, so they do not depend on how
# the vibration splits between X, Y and Z. That split changes when the fan
# sits differently on the table: across the three recorded sessions the RMS
# of the X axis ranged from 0.075 to 0.146 g, while the total stayed between
# 0.145 and 0.154 g.

TOTALS = ["rms_total", "peak_total", "domamp_total", "kurtosis_mean", "domfreq"]

TOTAL_NAMES = {
    "rms_total": "total vibration",
    "peak_total": "vibration peak",
    "domamp_total": "strength of the dominant frequency",
    "kurtosis_mean": "impacts (kurtosis)",
    "domfreq": "dominant frequency",
}


def derive_window(v):
    """The 5 total measures of one window (a dictionary with the columns)."""
    import math
    total = lambda kind: math.sqrt(sum(float(v[f"{a}_{kind}"]) ** 2 for a in "xyz"))
    domfreqs = sorted(float(v[f"{a}_domfreq"]) for a in "xyz")
    return {
        "rms_total": total("rms"),
        "peak_total": total("peak"),
        "domamp_total": total("domamp"),
        "kurtosis_mean": sum(float(v[f"{a}_kurtosis"]) for a in "xyz") / 3,
        "domfreq": domfreqs[1],
    }


def derive_table(df):
    """Adds the 5 total measures to a pandas table."""
    import numpy as np
    for kind in ("rms", "peak", "domamp"):
        df[f"{kind}_total"] = np.sqrt(sum(df[f"{a}_{kind}"] ** 2 for a in "xyz"))
    df["kurtosis_mean"] = sum(df[f"{a}_kurtosis"] for a in "xyz") / 3
    df["domfreq"] = df[[f"{a}_domfreq" for a in "xyz"]].median(axis=1)
    return df
