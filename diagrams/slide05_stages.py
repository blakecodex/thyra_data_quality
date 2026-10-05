"""slide 5: five stages, each with the test that closed it. run: python diagrams/slide05_stages.py"""
from matplotlib.patches import FancyBboxPatch
import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _style import canvas, save, BG, FG, DIM, ACC

stages = [
    ("1  Source feeds", "every hub-day complete;\na rerun changes nothing"),
    ("2  Features and backtest", "backtest uses only data\navailable at prediction time"),
    ("3  First model release", "service loads only a\nregistered model version"),
    ("4  Promotion controls", "a seeded worse-at-peak\ncandidate is held"),
    ("5  Monitoring", "a seeded feed change\npages a person"),
]
fig, ax = canvas(13.33, 1.9)
n, w, h = len(stages), 2.35, 0.8
gap = (13.33 - 0.4 - n * w) / (n - 1)
for i, (name, test) in enumerate(stages):
    x = 0.2 + i * (w + gap)
    ax.add_patch(FancyBboxPatch((x, 0.95), w, h, boxstyle="round,pad=0.02,rounding_size=0.06", fc=BG, ec=FG, lw=1.3))
    ax.text(x + w / 2, 0.95 + h / 2, name, ha="center", va="center", color=FG, fontsize=10.5, fontweight="bold")
    ax.text(x + w / 2, 0.78, "done when", ha="center", va="top", color=ACC, fontsize=8, style="italic")
    ax.text(x + w / 2, 0.55, test, ha="center", va="top", color=DIM, fontsize=9, linespacing=1.3)
    if i < n - 1:
        ax.annotate("", xy=(x + w + gap - 0.03, 1.35), xytext=(x + w + 0.03, 1.35), arrowprops=dict(arrowstyle="-|>", color=FG, lw=1.2))
save(fig, os.path.join(os.path.dirname(os.path.abspath(__file__)), "slide05_stages.png"))
