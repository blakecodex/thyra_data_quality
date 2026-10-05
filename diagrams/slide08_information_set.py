"""slide 8: what production knew at prediction time versus what the first backtest used. run: python diagrams/slide08_information_set.py"""
from matplotlib.patches import FancyBboxPatch
import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _style import canvas, save, BG, FG, DIM, ACC

fig, ax = canvas(13.33, 3.0)
# a timeline: prediction time, then days later the verified prices arrive
ax.annotate("", xy=(12.6, 1.5), xytext=(0.6, 1.5), arrowprops=dict(arrowstyle="-|>", color=FG, lw=1.4))
for x, label in [(1.4, "day-ahead close\nforecast made"), (4.6, "real-time prices\narrive preliminary"), (9.2, "verified prices\narrive days later")]:
    ax.plot([x, x], [1.35, 1.65], color=FG, lw=1.4)
    ax.text(x, 1.05, label, ha="center", va="top", color=DIM, fontsize=9.5, linespacing=1.3)
ax.text(0.6, 2.12, "production knew only this", color=ACC, fontsize=10, va="bottom")
ax.annotate("", xy=(6.9, 2.05), xytext=(0.6, 2.05), arrowprops=dict(arrowstyle="-", color=ACC, lw=3))
ax.text(7.1, 2.62, "the first backtest also used this", color="#E8A598", fontsize=10, va="bottom")
ax.annotate("", xy=(12.4, 2.55), xytext=(7.1, 2.55), arrowprops=dict(arrowstyle="-", color="#E8A598", lw=3))
ax.text(0.6, 0.15, "fix: the backtest reads the same information set production had. reported accuracy then equals deployable accuracy.", color=DIM, fontsize=9.5, va="bottom")
save(fig, os.path.join(os.path.dirname(os.path.abspath(__file__)), "slide08_information_set.png"))
