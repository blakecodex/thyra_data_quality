"""slide 6: the test strategy as three layers and one loop. run: python diagrams/slide06_strategy.py"""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from matplotlib.patches import FancyBboxPatch
from _style import canvas, save, BG, FG, DIM, ACC

fig, ax = canvas(13.33, 3.6)
# three layers, widest at the bottom: data tests, pipeline tests, model tests
layers = [
    (0.6, 0.25, 7.4, 0.85, "Data tests", "valid schema, complete hub-hours, correct time semantics"),
    (1.2, 1.2, 6.2, 0.85, "Pipeline tests", "repeatable transforms, no leakage, safe reruns"),
    (1.8, 2.15, 5.0, 0.85, "Model tests", "candidate beats champion by segment, coverage at target"),
]
for x, y, w, h, name, sub in layers:
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.06", fc=BG, ec=FG, lw=1.3))
    ax.text(x + 0.25, y + h - 0.24, name, ha="left", va="center", color=FG, fontsize=11, fontweight="bold")
    ax.text(x + 0.25, y + 0.24, sub, ha="left", va="center", color=DIM, fontsize=9.2)
ax.text(4.3, 3.25, "the quality contract: three layers, all must pass", ha="center", va="center", color=ACC, fontsize=10)
# the loop on the right: seed a defect -> check fails -> fix -> check passes -> trusted
loop = [(10.6, 3.0, "seed a defect"), (12.3, 1.95, "the check fails"), (10.6, 0.9, "fix and rerun"), (8.9, 1.95, "the check passes")]
for x, y, t in loop:
    ax.add_patch(FancyBboxPatch((x - 0.85, y - 0.28), 1.7, 0.56, boxstyle="round,pad=0.02,rounding_size=0.06", fc=BG, ec=ACC, lw=1.2))
    ax.text(x, y, t, ha="center", va="center", color=FG, fontsize=9.5)
arrows = [((11.35, 2.8), (12.1, 2.3)), ((12.1, 1.6), (11.35, 1.1)), ((9.85, 1.1), (9.1, 1.6)), ((9.1, 2.3), (9.85, 2.8))]
for (x0, y0), (x1, y1) in arrows:
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0), arrowprops=dict(arrowstyle="-|>", color=ACC, lw=1.2))
ax.text(10.6, 1.95, "a check is trusted\nonly after it has\nbeen seen to fail", ha="center", va="center", color=DIM, fontsize=8.8, linespacing=1.3)
save(fig, os.path.join(os.path.dirname(os.path.abspath(__file__)), "slide06_strategy.png"))
