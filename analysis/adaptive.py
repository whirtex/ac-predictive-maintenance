"""Adaptive detector: learns what is normal in place and keeps updating it.

A model trained once goes stale when the place or the conditions change. On
the bench, the same fan vibrated about 0.15 g on one table and about 0.10 g on
another, a bigger difference than an obstruction would cause. A warming motor
also changes the vibration slowly over more than 20 minutes.

So this detector:

  1. spends LEARNING_S learning what is normal where it sits;
  2. then detects. Each window goes through two tests, and one of them is
     enough to raise an alarm:
       - the Isolation Forest, over the 5 total measures (csv_format.TOTALS),
         says whether the combination looks normal;
       - the ruler says whether the total vibration, the peak or the strength
         of the dominant frequency moved more than RULER deviations away from
         normal. The Isolation Forest says whether a point is odd, but not how
         odd: far from normal its score saturates, and a vibration 30% higher
         once sat right at the threshold;
     The Isolation Forest alone raises an alarm only if it flags two windows
     in a row and some measure is at least MIN_Z_MODEL deviations from
     normal. Live, with a very tight normal, it flagged swings of 1.7 to 2.8
     deviations, about the size of the noise. The ruler fires at once, because
     it catches strong impacts;
  3. every UPDATE_S, relearns from the last MEMORY_S of normal windows. A slow
     change, such as warm-up or the weather of the day, enters the normal. A
     fast change, such as an obstruction, becomes an alarm.

The risk of an adaptive detector is getting used to a fault that grows
slowly. The protections:

  - a window flagged as abnormal never enters the normal, nor do the windows
    of the BLOCK_S after an alarm;
  - while there is a recent alarm, the model does not update;
  - the last DELAY_S are left out of each relearning, so the start of a fault,
    before it gets flagged, does not enter the normal;
  - the reference from the first learning is kept, and the detector reports
    how far the current normal has moved from it (drift). A slow wear shows up
    there even if the model got used to it.

The system alone cannot tell a persistent fault from a legitimate change of
position. After 3 minutes of persistent alarm, it asks for an inspection and
keeps the previous reference. Automatic adaptation continues only with
readings considered normal.
"""

from collections import deque

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from csv_format import TOTALS, derive_window, readable_name

LEARNING_S = 120       # initial learning in place
UPDATE_S = 60          # how often it relearns
MEMORY_S = 600         # how much of the recent past enters the normal
BLOCK_S = 30           # after an alarm, it does not learn for this long
DELAY_S = 30           # the most recent past stays out of the relearning
QUANTILE = 0.002       # fraction of the recent normal that would fall below the threshold
RULER = 6              # deviations the ruler tolerates
MIN_Z_MODEL = 3        # the model only raises an alarm if some measure passes this
FLOOR = 0.03           # the deviation never counts as less than 3% of the mean
MIN_WINDOWS = 40       # below this there is not enough data to train
PERSISTENCE_S = 180    # minimum time before asking for an inspection
PERSISTENT_FRACTION = 0.8  # minimum fraction of windows in alert within that time
MIN_PERSISTENCE_WINDOWS = 100
QUIET_GAP_S = 10       # a longer pause ends the persistent episode
STARTUP_S = 15         # the start of every learning from scratch is left out: it is
                       # the motor start-up, with jolts that widen the normal

# Measures the ruler watches: the intensity ones. Kurtosis and frequency are
# left to the Isolation Forest alone.
RULER_MEASURES = ["rms_total", "peak_total", "domamp_total"]


def describe(key, z, value, mean):
    """Short sentence about how far a measure moved from normal.

    Far from normal, deviations turn into meaningless numbers (one knock takes
    the kurtosis from 2 to 90, more than a thousand deviations); then the
    sentence uses how many times the normal instead.
    """
    name = readable_name(key)
    if abs(z) > 20 and mean > 0:
        times = value / mean
        text = f"{name}: {times:.1f} times normal" if times >= 1 else \
               f"{name}: {100 * (1 - times):.0f}% below normal"
    else:
        direction = "above" if z > 0 else "below"
        text = f"{name}: {abs(z):.1f} deviations {direction} normal"
    return text


class AdaptiveDetector:
    def __init__(self, learning_s=LEARNING_S, update_s=UPDATE_S,
                 memory_s=MEMORY_S, block_s=BLOCK_S, quantile=QUANTILE):
        self.learning_s = learning_s
        self.update_s = update_s
        self.memory_s = memory_s
        self.block_s = block_s
        self.quantile = quantile
        self.windows = deque()   # [t, measures, can_learn]
        self.model = None
        self.start = None
        self.last_update = None
        self.block_until = float("-inf")
        self.reference = None    # mean total vibration of the first learning
        self.updates = []        # one entry per (re)learning
        self.model_flagged_before = False   # did the Isolation Forest flag the previous window?
        self.alert_start = None
        self.last_alert = None
        self.recent_alerts = deque()  # (t, outside), during the persistent change
        self.investigate = False

    def _persistent_change(self, t, outside):
        """Signals once when an alarm calls for an inspection."""
        if outside:
            if self.alert_start is None:
                self.alert_start = t
            self.last_alert = t
        elif self.last_alert is not None and t - self.last_alert > QUIET_GAP_S:
            self.alert_start = None
            self.last_alert = None
            self.recent_alerts.clear()
            self.investigate = False

        if self.alert_start is None:
            return False
        self.recent_alerts.append((t, outside))
        while self.recent_alerts and self.recent_alerts[0][0] < t - PERSISTENCE_S:
            self.recent_alerts.popleft()
        persistent = (outside and t - self.alert_start >= PERSISTENCE_S
                      and len(self.recent_alerts) >= MIN_PERSISTENCE_WINDOWS
                      and sum(alarm for _, alarm in self.recent_alerts)
                      / len(self.recent_alerts) >= PERSISTENT_FRACTION)
        new_escalation = persistent and not self.investigate
        if persistent:
            self.investigate = True
        return new_escalation

    def _train(self, t):
        useful = [x for tt, x, ok in self.windows
                  if ok and t - self.memory_s <= tt <= t - DELAY_S]
        if self.model is None:
            # in the learning from scratch there is no alarm yet: use everything but the start-up
            useful = [x for tt, x, ok in self.windows if ok]
        if len(useful) < MIN_WINDOWS:
            return False
        table = pd.DataFrame(useful, columns=TOTALS)
        scaler = StandardScaler().fit(table)
        forest = IsolationForest(n_estimators=150, random_state=0)
        forest.fit(scaler.transform(table))
        scores = forest.score_samples(scaler.transform(table))
        # Robust center and spread: the median and the median absolute
        # deviation (MAD, converted to the scale of the standard deviation). A
        # short run of jolts, such as the motor start-up, does not move the
        # median or widen the MAD, unlike the mean and the standard
        # deviation: live, the start-up inside the learning left the ruler
        # 51% above normal.
        mean = table.median()
        mad = 1.4826 * (table - mean).abs().median()
        dev = np.maximum(mad.fillna(0), FLOOR * mean.abs())
        previous = self.model["rms_mean"] if self.model else None
        kind = "update" if self.model else "initial"
        self.model = {
            "scaler": scaler,
            "forest": forest,
            "threshold": float(np.quantile(scores, self.quantile)),
            "mean": mean,
            "dev": dev.replace(0, np.nan),
            "rms_mean": float(mean["rms_total"]),
            "rms_dev": float(mad["rms_total"]),
        }
        if self.reference is None:
            self.reference = self.model["rms_mean"]
        self.last_update = t
        self.updates.append({
            "t": t,
            "kind": kind,
            "rms_mean": self.model["rms_mean"],
            "rms_dev": self.model["rms_dev"],
            "ruler": self.model["rms_mean"] + RULER * float(dev["rms_total"]),
            "limit": -self.model["threshold"],
            "windows": len(useful),
            "change": None if previous is None else 100 * (self.model["rms_mean"] / previous - 1),
            "drift": 100 * (self.model["rms_mean"] / self.reference - 1),
        })
        return True

    def _prune(self, t):
        while self.windows and self.windows[0][0] < t - self.memory_s:
            self.windows.popleft()

    def add(self, t, window):
        """Takes one window (a dictionary with the CSV columns) at time t.

        Returns a dictionary with the phase ('learning' or 'detecting') and,
        while detecting, whether the window is outside the normal, the degree
        of anomaly, the limit, the measure that moved the most and the drift
        since the installation.
        """
        measures = derive_window(window)
        x = [measures[c] for c in TOTALS]
        if self.start is None:
            self.start = t

        if self.model is None:
            self.windows.append([t, x, t - self.start >= STARTUP_S])
            self._prune(t)
            if t - self.start >= self.learning_s:
                self._train(t)
            return {"phase": "learning", "measures": measures,
                    "remaining": max(0.0, self.learning_s - (t - self.start))}

        m = self.model
        table = pd.DataFrame([x], columns=TOTALS)
        score = float(m["forest"].score_samples(m["scaler"].transform(table))[0])
        z = ((table.iloc[0] - m["mean"]) / m["dev"]).fillna(0)
        model_now = score < m["threshold"]
        by_model = (model_now and self.model_flagged_before
                    and bool((z.abs() >= MIN_Z_MODEL).any()))
        self.model_flagged_before = model_now
        by_ruler = bool((z[RULER_MEASURES].abs() > RULER).any())
        outside = by_model or by_ruler
        reason = " and ".join(n for n, v in (("model", by_model), ("ruler", by_ruler)) if v)

        # The text shows the measure that fired: if it was the ruler, the one
        # that moved the most among those it watches; if it was only the
        # model, the one that moved the most overall.
        candidates = z[RULER_MEASURES] if by_ruler else z
        key = candidates.abs().idxmax()
        detail = describe(key, z[key], measures[key], m["mean"][key])

        if outside:
            self.block_until = t + self.block_s
        new_escalation = self._persistent_change(t, outside)
        # Only what became an alarm stays out of the normal. A small change
        # that the model finds odd but that does not reach an alarm enters and
        # gets absorbed: before, a fan that came loose and moved 5% in
        # position was flagged for minutes without ever being learned.
        self.windows.append([t, x, (not outside) and t >= self.block_until])
        self._prune(t)
        if t - self.last_update >= self.update_s and t >= self.block_until:
            self._train(t)

        return {
            "phase": "detecting",
            "measures": measures,
            "outside": outside,
            "investigate": self.investigate,
            "new_escalation": new_escalation,
            "alert_time_s": t - self.alert_start if self.investigate else None,
            "reason": reason,
            "anomaly": -score,
            "limit": -m["threshold"],
            "detail": detail,
            "rms_mean": m["rms_mean"],
            "rms_dev": m["rms_dev"],
            "ruler": m["rms_mean"] + RULER * float(m["dev"]["rms_total"]),
            "drift": 100 * (m["rms_mean"] / self.reference - 1),
        }
