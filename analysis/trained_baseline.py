"""Trained-baseline detector: learns the normal once and does not relearn.

Decision of 6 November 2026 (docs/design-decisions.md). The adaptive
detector gets used to a fault that grows slowly. This one is trained by
whoever installs the unit, right after maintenance, with healthy runs in
several conditions (cold and warm motor, cold and hot days), and then stays
frozen: whatever leaves the trained normal becomes an alarm, the slow fault
included.

What it watches, in every ~1.2 s window:
  - the 5 total vibration measures (csv_format.TOTALS); the strength ones
    (vibration, peak and strength of the dominant frequency) count only
    when they rise.
The current is still recorded, but it left the alarm on 12 November (see
RISE_ONLY and MEASURES below).
The tachometer speed left on 12 November: on the same motor it read 0, 3000,
4300 and 4900 rpm in different sessions, depending on how the yellow wire
sat. The speed already shows in the dominant frequency of the vibration
(domfreq).

The room climate (air temperature and humidity, from the DHT11) raises no
alarm: it chooses which part of the training to compare with. For each
window, the normal is that of the NEIGHBORS training windows with the most
similar climate. So if the fan always turns a little differently on a hot
day, that is normal on a hot day. Recordings without climate use the whole
training.

Three questions per window, and one is enough for an alarm:
  1. ruler: did the vibration, the peak or the strength of the dominant
     frequency rise more than RULER spreads above the normal of that
     climate? Catches the abrupt fault;
  2. Isolation Forest, over the deviations of all measures: is the
     combination unusual? It only counts on two consecutive windows with
     some measure at MODEL_MIN_Z spreads or more, as in the adaptive one;
  3. slow look: did the median of the last SLOW_S seconds of each measure in
     SLOW_MEASURES leave the range these medians had in training? Catches
     the fault that grows slowly, too small for a single window.

The first WARMUP_S seconds of every recording are the motor warming up:
they stay out of training and raise no alarm. In the night recording of
6 November, the vibration rose from 0.13 to 0.18 g and the current fell from
165 to 140 mA in the first 4 minutes.

If the climate now is far from everything training saw (more than 1 degree
or 5 points of humidity on the CLIMATE_SCALE), the window comes out marked
as new_climate: its alarm is worth less, and the right thing is to train in
that climate too.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import NearestNeighbors

from csv_format import CLIMATE, COLUMNS, TOTALS, derive_table

MEASURES = TOTALS
# The current stays recorded, but out of the alarm since 12 November: on the
# same bench, with no fault at all, it was 154 mA in one session (11 November)
# and 142 mA in another (12 November), and none of the three recorded faults
# (unbalance, loose part, obstruction) moved it. With it in the slow look,
# the healthy session of 11 November gave 100% alarm.
# The vibration strength measures count only when they rise: vibrating less
# than normal is not a fault (the three recorded faults raised the strength
# or changed the frequency; none lowered it), and the short drops of the
# board gave false alarms.
RISE_ONLY = ["rms_total", "peak_total", "domamp_total"]
RULER_MEASURES = ["rms_total", "peak_total", "domamp_total"]
# The slow look watches what wear changes little by little: the vibration
# energy and the frequency (which also gives the speed). The peak and the
# kurtosis stay with the ruler and the Isolation Forest only: they measure
# shocks. On the night of 6 November, a stretch with the peak 10% above and
# the same total vibration (a bump on the table, probably) set off the slow
# look with no fault at all.
SLOW_MEASURES = ["rms_total", "domamp_total", "domfreq"]
CLIMATE_SCALE = np.array([1.0, 5.0])   # 1 degree weighs as much as 5 points of humidity

WARMUP_S = 300         # motor warming up: out of training and no alarm
NEIGHBORS = 600        # training windows with the most similar climate (~12 min)
RULER = 6              # spreads the ruler tolerates, as in the adaptive one
MODEL_MIN_Z = 3
QUANTILE = 0.002       # fraction of training below the Isolation Forest threshold
FLOOR = 0.03           # the spread of a window never counts as less than 3%
SLOW_S = 180           # window of the slow-look median
SLOW_FLOOR = 0.01      # the spread of the slow median never counts as less than 1%
SLOW_MARGIN = 1.25     # slack over the largest slow deviation seen in training
SLOW_MIN_LIMIT = 4.0   # the slow limit is never below this, in spreads
SLOW_MIN_WINDOWS = 100  # minimum windows in the slow median (~2 min)
SWAY_HZ = 10           # below this, the dominant frequency is the sway of the base


def read_csv(path):
    """Reads a recording of esp32_acquisition, with or without the climate
    columns, and returns a table with t (seconds since the start) and the
    measures."""
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            fields = line.rstrip("\n").split(",")
            if line.startswith("#") or fields[0] in ("datetime", "data_hora"):
                continue
            if len(fields) == len(COLUMNS):
                fields += [""] * len(CLIMATE)
            if len(fields) == len(COLUMNS) + len(CLIMATE):
                rows.append(fields)
    df = pd.DataFrame(rows, columns=COLUMNS + CLIMATE)
    for c in COLUMNS[1:] + CLIMATE:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if df.datetime.str.startswith("boot+").all():
        seconds = df.datetime.str[5:].astype(float)
    else:
        times = pd.to_datetime(df.datetime, errors="coerce")
        seconds = (times - times.iloc[0]).dt.total_seconds()
    # the timestamp has 1 s resolution; the real duration of each window
    # comes from the rate
    df["t"] = seconds.iloc[0] + np.concatenate([[0], np.cumsum(512 / df.rate_hz.values[1:])])
    df = derive_table(df.dropna(subset=["rate_hz"]).reset_index(drop=True))
    return df


def slow_median(df, slow_s=SLOW_S, warmup_s=WARMUP_S):
    """Causal moving median of each measure over the last slow_s seconds,
    without the warm-up windows. Until 12 November the warm-up entered the
    median: right after it, the slow rhythm of the board, which dominates
    the warm-up, pulled the median frequency to 5 Hz, and the slow limit of
    the frequency sat at ~110 spreads, too wide to see the loose part
    (46 -> 93 Hz).

    In the frequency, windows below SWAY_HZ also stay out: they are the slow
    sway of the base (3 to 5 Hz), not the machine. On the night of
    12 November, a 3 min stretch with that sway in more than half of the
    windows, with no fault, took the median frequency to 5 Hz and inflated
    the same limit."""
    time = pd.to_datetime(df.t, unit="s")
    measures = df[MEASURES].copy()
    measures[(df.t - df.t.iloc[0]).values < warmup_s] = np.nan
    measures.loc[measures.domfreq < SWAY_HZ, "domfreq"] = np.nan
    slow = measures.set_index(time).rolling(f"{slow_s}s", min_periods=SLOW_MIN_WINDOWS).median()
    return slow.reset_index(drop=True)


class TrainedBaseline:
    def __init__(self, neighbors=NEIGHBORS, warmup_s=WARMUP_S, slow_s=SLOW_S):
        self.neighbors = neighbors
        self.warmup_s = warmup_s
        self.slow_s = slow_s
        self._cache = {}
        self._rise_only = [MEASURES.index(m) for m in RISE_ONLY]

    # --- training ----------------------------------------------------------

    def train(self, recordings):
        """recordings: a list of read_csv() tables, all of healthy operation,
        or of tuples (table, from_s, to_s) to use only a stretch of it. The
        stretch counts the time since the start of the recording, and the
        warm-up is always the one at the start of the recording."""
        parts = []
        for item in recordings:
            df, from_s, to_s = item if isinstance(item, tuple) else (item, 0, np.inf)
            slow = slow_median(df, self.slow_s, self.warmup_s)
            since = (df.t - df.t.iloc[0]).values
            used = (since >= max(self.warmup_s, from_s)) & (since < to_s)
            part = df.loc[used, MEASURES + CLIMATE].reset_index(drop=True)
            part[[m + "_slow" for m in MEASURES]] = slow.loc[used].values
            parts.append(part)
        training = pd.concat(parts, ignore_index=True)
        self.X = training[MEASURES].to_numpy(float)
        self.L = training[[m + "_slow" for m in MEASURES]].to_numpy(float)
        self.C = training[CLIMATE].to_numpy(float)
        self.with_climate = ~np.isnan(self.C).any(axis=1)
        if self.with_climate.sum() >= self.neighbors:
            self._neighborhood = NearestNeighbors(n_neighbors=self.neighbors).fit(
                self.C[self.with_climate] / CLIMATE_SCALE)
        else:
            self._neighborhood = None
        self.n_train = len(training)

        z, zl, _ = self._deviations(self.X, self.L, self.C)
        self.forest = IsolationForest(n_estimators=200, random_state=0).fit(z)
        self.threshold = float(np.quantile(self.forest.score_samples(z), QUANTILE))
        largest = np.nanquantile(np.abs(zl), 0.999, axis=0)
        self.slow_limit = np.maximum(SLOW_MIN_LIMIT, SLOW_MARGIN * largest)
        self.climate_range = (np.nanmin(self.C, axis=0), np.nanmax(self.C, axis=0))
        return self

    # --- the normal of a climate --------------------------------------------

    def _normal(self, climate):
        """Center and spread of each measure, for the window and for the slow
        median, in the given climate, and the distance to the nearest
        training climate."""
        key = None if np.isnan(climate).any() else tuple(np.round(climate, 1))
        if key in self._cache:
            return self._cache[key]
        if key is None or self._neighborhood is None:
            idx = np.arange(len(self.X))
            distance = np.nan
        else:
            d, i = self._neighborhood.kneighbors([np.asarray(climate) / CLIMATE_SCALE])
            idx = np.flatnonzero(self.with_climate)[i[0]]
            distance = float(d[0, 0])
        x, slow = self.X[idx], self.L[idx]
        center = np.nanmedian(x, axis=0)
        spread = np.maximum(1.4826 * np.nanmedian(np.abs(x - center), axis=0), FLOOR * np.abs(center))
        center_s = np.nanmedian(slow, axis=0)
        spread_s = np.maximum(1.4826 * np.nanmedian(np.abs(slow - center_s), axis=0),
                              SLOW_FLOOR * np.abs(center_s))
        self._cache[key] = (center, spread, center_s, spread_s, distance)
        return self._cache[key]

    def _deviations(self, X, L, C):
        z = np.empty_like(X)
        zl = np.empty_like(L)
        dist = np.empty(len(X))
        for k in range(len(X)):
            center, spread, center_s, spread_s, distance = self._normal(C[k])
            z[k] = (X[k] - center) / spread
            zl[k] = (L[k] - center_s) / spread_s
            dist[k] = distance
        z[:, self._rise_only] = np.maximum(z[:, self._rise_only], 0)
        zl[:, self._rise_only] = np.maximum(zl[:, self._rise_only], 0)
        return np.nan_to_num(z), zl, dist

    # --- detection -----------------------------------------------------------

    def detect(self, df, from_s=0, to_s=np.inf):
        """Runs a recording (a read_csv table) through the detector, window by
        window, in order, and returns a table with one row per window of the
        stretch from from_s to to_s seconds. The slow median uses the past of
        the whole recording, as it would live."""
        since = (df.t - df.t.iloc[0]).values
        df = df.assign(_since=since)
        slow = slow_median(df, self.slow_s, self.warmup_s)
        stretch = (since >= from_s) & (since < to_s)
        df = df[stretch].reset_index(drop=True)
        slow = slow[stretch].reset_index(drop=True)
        z, zl, dist = self._deviations(df[MEASURES].to_numpy(float), slow.to_numpy(float),
                                       df[CLIMATE].to_numpy(float))
        scores = self.forest.score_samples(z)
        unusual = scores < self.threshold
        previous = np.concatenate([[False], unusual[:-1]])
        by_model = unusual & previous & (np.abs(z) >= MODEL_MIN_Z).any(axis=1)
        col = [MEASURES.index(m) for m in RULER_MEASURES]
        by_ruler = (np.abs(z[:, col]) > RULER).any(axis=1)
        slows = [MEASURES.index(m) for m in SLOW_MEASURES]
        by_slow = (np.abs(np.nan_to_num(zl[:, slows])) > self.slow_limit[slows]).any(axis=1)
        warming = (df._since < self.warmup_s).values
        out = (by_model | by_ruler | by_slow) & ~warming

        # the measure that weighed most, for the alarm message
        slow_only = np.zeros(len(MEASURES))
        slow_only[slows] = 1
        ratio = np.maximum(np.abs(z) / RULER, slow_only * np.abs(np.nan_to_num(zl)) / self.slow_limit)
        return pd.DataFrame({
            "t": df.t.values,
            "out": out,
            "ruler": by_ruler & ~warming,
            "model": by_model & ~warming,
            "slow": by_slow & ~warming,
            "warming": warming,
            "measure": [MEASURES[i] for i in ratio.argmax(axis=1)],
            "new_climate": np.nan_to_num(dist, nan=0.0) > 1.0,
        })


def scale_vibration(df, factor):
    """Multiplies the vibration intensity measures by factor (a number or a
    vector, one entry per window): the simulated fault."""
    df = df.copy()
    f = np.asarray(factor, float)
    for a in "xyz":
        for k in ("rms", "peak", "domamp"):
            df[f"{a}_{k}"] = df[f"{a}_{k}"] * f
    return derive_table(df)
