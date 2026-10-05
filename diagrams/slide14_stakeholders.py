"""slide 14: the stakeholder map, influence against interest, with how each quadrant was handled. run: python diagrams/slide14_stakeholders.py"""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from matplotlib.patches import FancyBboxPatch
from _style import canvas, save, BG, FG, DIM, ACC

fig, ax = canvas(13.33, 4.6)
x0, y0, W, H = 1.2, 0.5, 11.0, 3.6
# axes
ax.annotate("", xy=(x0 + W + 0.3, y0), xytext=(x0 - 0.05, y0), arrowprops=dict(arrowstyle="-|>", color=FG, lw=1.3))
ax.annotate("", xy=(x0, y0 + H + 0.3), xytext=(x0, y0 - 0.05), arrowprops=dict(arrowstyle="-|>", color=FG, lw=1.3))
ax.text(x0 + W / 2, y0 - 0.3, "interest in the day-to-day quality work  →", ha="center", va="top", color=DIM, fontsize=11)
ax.text(x0 - 0.3, y0 + H / 2, "influence on the release  →", ha="center", va="center", color=DIM, fontsize=11, rotation=90)
ax.plot([x0 + W / 2, x0 + W / 2], [y0, y0 + H], color=DIM, lw=0.8, ls="--")
ax.plot([x0, x0 + W], [y0 + H / 2, y0 + H / 2], color=DIM, lw=0.8, ls="--")
quads = [
    (x0 + 0.2, y0 + H / 2 + 0.2, "HIGH INFLUENCE, LOW INTEREST", "Client leadership\nset the go-live date", "Keep satisfied: a one-page status,\nthe pilot label in writing, no surprises."),
    (x0 + W / 2 + 0.2, y0 + H / 2 + 0.2, "HIGH INFLUENCE, HIGH INTEREST", "Client risk desk\nused the forecasts daily", "Manage closely: the daily report, the band\nshown with the number, same-day answers on failures."),
    (x0 + 0.2, y0 + 0.2, "LOW INFLUENCE, LOW INTEREST", "Client IT\naccess and cloud accounts", "Monitor: access requests early, one owner,\nnothing blocked at release time."),
    (x0 + W / 2 + 0.2, y0 + 0.2, "LOW INFLUENCE, HIGH INTEREST", "Data scientists and data engineers\nthe delivery team", "Keep involved: MRs with a why, one reproducible\nfailing case, standards written down."),
]
for x, y, head, who, how in quads:
    ax.text(x, y + H / 2 - 0.3, head, color=ACC, fontsize=10.5, fontweight="bold", va="top")
    ax.text(x, y + H / 2 - 0.68, who, color=FG, fontsize=12.5, va="top", linespacing=1.3)
    ax.text(x, y + 0.1, how, color=DIM, fontsize=10.5, va="bottom", linespacing=1.35)
save(fig, os.path.join(os.path.dirname(os.path.abspath(__file__)), "slide14_stakeholders.png"))
