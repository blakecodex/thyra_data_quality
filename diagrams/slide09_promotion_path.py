"""slide 9: the model promotion path, with one release decision as a callout. run: python diagrams/slide09_promotion_path.py"""
from matplotlib.patches import FancyBboxPatch
import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _style import canvas, save, BG, FG, DIM, ACC

FAIL = "#E8A598"
steps = ["Candidate\nmodel", "MLflow run", "Merge request", "CI backtest\nvs champion", "Release gate", "Human\napproval", "Release"]
fig, ax = canvas(13.33, 3.0)
n, w, h, y = len(steps), 1.6, 0.8, 2.0
gap = (13.33 - 0.4 - n * w) / (n - 1)
for i, name in enumerate(steps):
    x = 0.2 + i * (w + gap)
    bold = name == "Release gate"
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.06", fc=BG, ec=FG, lw=2.2 if bold else 1.3))
    ax.text(x + w / 2, y + h / 2, name, ha="center", va="center", color=FG, fontsize=9.8, linespacing=1.2, fontweight="bold" if bold else "normal")
    if i < n - 1:
        ax.annotate("", xy=(x + w + gap - 0.03, y + h / 2), xytext=(x + w + 0.03, y + h / 2), arrowprops=dict(arrowstyle="-|>", color=FG, lw=1.2))
# the fail branch under the gate
gx = 0.2 + 4 * (w + gap) + w / 2
ax.annotate("", xy=(gx, 1.2), xytext=(gx, y - 0.03), arrowprops=dict(arrowstyle="-|>", color=FAIL, lw=1.4))
ax.text(gx, 1.1, "fail = held\nerror by hub and hour block,\nbootstrap band, interval coverage", ha="center", va="top", color=FAIL, fontsize=9, linespacing=1.3)
# one release decision, as a callout
cx, cy, cw, ch = 10.1, 0.1, 3.05, 1.35
ax.add_patch(FancyBboxPatch((cx, cy), cw, ch, boxstyle="round,pad=0.02,rounding_size=0.06", fc=BG, ec=FAIL, lw=1.4))
ax.text(cx + 0.2, cy + ch - 0.22, "One release decision", color=FG, fontsize=10, fontweight="bold", va="center")
ax.text(cx + 0.2, cy + ch - 0.55, "average error: improved", color=DIM, fontsize=9.5, va="center")
ax.text(cx + 0.2, cy + ch - 0.83, "peak hours: degraded", color=DIM, fontsize=9.5, va="center")
ax.text(cx + 0.2, cy + ch - 1.13, "decision: held", color=FAIL, fontsize=9.5, fontweight="bold", va="center")
save(fig, os.path.join(os.path.dirname(os.path.abspath(__file__)), "slide09_promotion_path.png"))
