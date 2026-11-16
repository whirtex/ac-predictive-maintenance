"""Runs the trained baseline over the board recordings of 11 and 12 November:
four healthy stretches and the three real faults (unbalance, loose part and
obstruction).

Two trainings. The default, since 12 November: the night of 12 November
(first 200 min, ~26 C) plus the first half of the hot afternoon of
12 November (~30 C), so that the model knows both climates; the second half
of the afternoon is kept for testing. And, for comparison, the night only.
For each stretch, the fraction of windows out of the normal after warm-up,
how much comes from each test and the measure that weighed most.

Output: results/real_faults_evaluation.txt

Usage: .venv/bin/python analysis/evaluation/evaluate_real_faults.py
"""
import io
import os
import sys
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths  # noqa: E402,F401
import trained_baseline as tb  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
D = os.path.join(ROOT, "data") + os.sep
L = lambda n: tb.read_csv(D + n + ".csv")  # noqa: E731
night, heat = L("board-bench-night"), L("board-bench-hot-afternoon")
CASES = [  # name, table, from, to, expected
    ("night end (healthy)", night, 200*60, 1e9, "healthy"),
    ("heat 2nd half (healthy)", heat, 28*60, 1e9, "healthy"),
    ("board-place6 11 Nov (healthy)", L("board-place6"), 0, 1e9, "healthy"),
    ("after the tape flew (healthy)", L("board-tape-firm"), 20*60, 1e9, "healthy"),
    ("firm tape (unbalance)", L("board-tape-firm"), 0, 16.2*60, "fault"),
    ("loose tape (loose part)", L("board-tape-loose"), 0, 1e9, "fault"),
    ("obstruction", L("board-front-obstructed"), 0, 1e9, "fault"),
]


def run(training, label):
    b = tb.TrainedBaseline().train(training)
    print(f"--- {label}  (training {b.n_train} windows)")
    for name, df, start, end, exp in CASES:
        r = b.detect(df, start, end)
        r = r[~r.warming]
        mc = r.measure[r.out].value_counts().head(2).to_dict()
        print(f"  {name:32s} {exp:7s} out {100*r.out.mean():5.1f}%  ruler {100*r.ruler.mean():5.1f}"
              f" model {100*r.model.mean():5.1f} slow {100*r.slow.mean():5.1f}  {mc}")


if __name__ == "__main__":
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        run([(night, 0, 200*60), (heat, 0, 28*60)], "default training: night + hot afternoon, 1st half")
        run([(night, 0, 200*60)], "night only, for comparison")
    text = buffer.getvalue()
    print(text, end="")
    with open(os.path.join(ROOT, "results", "real_faults_evaluation.txt"), "w", encoding="utf-8") as f:
        f.write(text)
