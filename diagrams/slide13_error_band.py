"""slide 13: daily forecast error against the band the backtest set, on the snapshot's held-out and production windows.

run from the repository root: python diagrams/slide13_error_band.py
the band is the mean daily error of the champion on the last sixty training days, plus and minus two standard
deviations; three consecutive days outside it is the review trigger. the gate scored january 1 to 23; from
january 24 the data is what production saw after the release, which was the winter storm of late january 2026.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import numpy as np
import pandas as pd
from _style import canvas, save, BG, FG, DIM, ACC, plt
from thyra.gate import build_run, load_suite

FAIL = "#E8A598"
suite = load_suite(os.path.join(REPO, "gate.yaml"))
run = build_run(int(suite.get("seed", 7)), [], suite)
m = run.champion


def daily_mae(df):
    e = np.abs(df["y"].to_numpy() - m.predict(df))
    return pd.Series(e).groupby(pd.to_datetime(df["day"].to_numpy())).mean()


ref = run.train[run.train["day"] >= run.train["day"].max() - pd.Timedelta(days=60)]
band = daily_mae(ref)
lo, hi = max(band.mean() - 2 * band.std(), 0.5), band.mean() + 2 * band.std()
held = daily_mae(run.test)
prod = daily_mae(run.after)
series = pd.concat([held, prod])
outside = series[(series > hi) | (series < lo)]
# the review trigger: the third consecutive day outside the band
streak, trigger = 0, None
for day, v in series.items():
    streak = streak + 1 if (v > hi or v < lo) else 0
    if streak == 3 and trigger is None:
        trigger = day

fig, ax = plt.subplots(figsize=(13.33, 3.6), dpi=200)
fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
ax.set_yscale("log")
ax.axhspan(lo, hi, color=ACC, alpha=0.18, lw=0)
ax.axhline(band.mean(), color=ACC, lw=1, ls="--")
ax.plot(held.index, held.values, color=FG, lw=1.6)
ax.plot(prod.index, prod.values, color=FG, lw=1.6)
ax.scatter(outside.index, outside.values, color=FAIL, s=30, zorder=3)
split = prod.index.min()
ax.axvline(split, color=DIM, lw=1, ls=":")
ax.text(held.index.min(), hi * 1.25, "held-out window: the gate's evidence", color=DIM, fontsize=9, va="bottom")
ax.text(split, hi * 1.25, "  production: after the release", color=DIM, fontsize=9, va="bottom")
if trigger is not None:
    ax.annotate("third day outside: review", xy=(trigger, series[trigger]), xytext=(trigger - pd.Timedelta(days=9), series.max() * 0.9),
                color=FAIL, fontsize=9.5, arrowprops=dict(arrowstyle="-|>", color=FAIL, lw=1.1), va="top")
ax.text(held.index.min(), band.mean() * 0.82, "band mean", color=ACC, fontsize=8.5, va="top")
for sp in ax.spines.values():
    sp.set_color(DIM)
ax.tick_params(colors=DIM, labelsize=9, which="both")
ax.set_ylabel("daily mean absolute error, $/MWh (log)", color=DIM, fontsize=10)
ax.set_title("daily error of the champion against the backtest band (mean of the last 60 training days, plus and minus two standard deviations)", color=DIM, fontsize=10, loc="left")
ax.set_xlim(held.index.min() - pd.Timedelta(days=1), series.index.max() + pd.Timedelta(days=4))
fig.autofmt_xdate()
save(fig, os.path.join(REPO, "diagrams", "slide13_error_band.png"))
print("band", round(lo, 2), round(hi, 2), "days outside", len(outside), "of", len(series), "trigger", trigger.date() if trigger is not None else None)
