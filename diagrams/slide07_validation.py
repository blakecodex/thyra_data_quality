"""slide 7: one record's path through validation, with the quarantine branch. run: python diagrams/slide07_validation.py"""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from matplotlib.patches import FancyBboxPatch
from _style import canvas, save, BG, FG, DIM, ACC

fig, ax = canvas(13.33, 3.4)
steps = [
    ("inbound\nrecord", ""),
    ("typed contract", "fields, units, ranges,\ntimestamp rules"),
    ("completeness", "24 hours per hub-day\n23 and 25 on DST days"),
    ("reconciliation", "preliminary vs verified\nprices, days later"),
    ("idempotent load", "a file loaded twice\nchanges nothing"),
    ("feature\ngeneration", ""),
]
n, w, h, y = len(steps), 1.75, 0.8, 2.2
gap = (13.33 - 0.4 - n * w) / (n - 1)
for i, (name, sub) in enumerate(steps):
    x = 0.2 + i * (w + gap)
    edge = DIM if i in (0, n - 1) else FG
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.06", fc=BG, ec=edge, lw=1.3))
    ax.text(x + w / 2, y + h / 2, name, ha="center", va="center", color=FG, fontsize=10, fontweight="bold" if 0 < i < n - 1 else "normal", linespacing=1.2)
    if sub:
        ax.text(x + w / 2, y - 0.12, sub, ha="center", va="top", color=DIM, fontsize=8.6, linespacing=1.3)
    if i < n - 1:
        ax.annotate("", xy=(x + w + gap - 0.03, y + h / 2), xytext=(x + w + 0.03, y + h / 2), arrowprops=dict(arrowstyle="-|>", color=FG, lw=1.2))
# the quarantine branch under the contract and reconciliation steps
qx = 0.2 + 1 * (w + gap) + w / 2
ax.annotate("", xy=(qx, 0.75), xytext=(qx, 1.35), arrowprops=dict(arrowstyle="-|>", color="#E8A598", lw=1.2))
ax.add_patch(FancyBboxPatch((qx - 2.2, 0.15), 4.4, 0.6, boxstyle="round,pad=0.02,rounding_size=0.06", fc=BG, ec="#E8A598", lw=1.2))
ax.text(qx, 0.45, "quarantine with a reason code\nhour_before_day · hour_beyond_day · unit_not_usd_mwh", ha="center", va="center", color="#E8A598", fontsize=8.8, linespacing=1.3)
cx = 0.2 + 4 * (w + gap) + w / 2
ax.annotate("", xy=(cx, 0.75), xytext=(cx, 1.35), arrowprops=dict(arrowstyle="-|>", color="#E8A598", lw=1.2))
ax.add_patch(FancyBboxPatch((cx - 1.6, 0.15), 3.2, 0.6, boxstyle="round,pad=0.02,rounding_size=0.06", fc=BG, ec="#E8A598", lw=1.2))
ax.text(cx, 0.45, "two copies that disagree\nare held for a person", ha="center", va="center", color="#E8A598", fontsize=8.8, linespacing=1.3)
save(fig, os.path.join(os.path.dirname(os.path.abspath(__file__)), "slide07_validation.png"))
