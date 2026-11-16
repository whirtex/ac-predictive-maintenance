"""Puts the subfolders of analysis/ on the import path.

What runs the bench (record, train, check, monitor and the detector) sits
directly in analysis/. The rest sits in subfolders:
  evaluation/  the evaluations behind the numbers of the article
  figures/     the figures of the article
  ap1/         the first-stage method (adaptive detector, two baselines) and
               its panel; the adaptive detector still enters the article's
               comparison

A script in a subfolder starts with:
    sys.path.insert(0, <analysis folder>)
    import paths
and then imports any module of any subfolder by name.
"""

import os
import sys

ANALYSIS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ANALYSIS)
SUBFOLDERS = ("evaluation", "figures", "ap1")

for _p in SUBFOLDERS:
    _c = os.path.join(ANALYSIS, _p)
    if _c not in sys.path:
        sys.path.insert(1, _c)
