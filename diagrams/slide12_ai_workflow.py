"""slide 12: the ai workflow around the gate, with the filter and the person. run: python diagrams/slide12_ai_workflow.py"""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from matplotlib.patches import FancyBboxPatch
from _style import canvas, save, BG, FG, DIM, ACC

fig, ax = canvas(13.33, 3.15)
steps = [
    ("gate report", "JSON: each check,\nits value, its threshold", FG),
    ("diagnosis", "computed, not guessed:\nwhich checks failed,\nmost upstream first", FG),
    ("language model", "drafts the incident note\nin plain words", ACC),
    ("text filter", "no number absent from\nthe report · no changed\nthreshold · no decision word", "#E8A598"),
    ("a person", "approves, edits\nor rejects", FG),
    ("incident note", "written only\non approval", FG),
]
n, w, h, y = len(steps), 1.8, 0.8, 1.85
gap = (13.33 - 0.4 - n * w) / (n - 1)
for i, (name, sub, col) in enumerate(steps):
    x = 0.2 + i * (w + gap)
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.06", fc=BG, ec=col, lw=2.0 if col != FG else 1.3))
    ax.text(x + w / 2, y + h / 2, name, ha="center", va="center", color=FG, fontsize=10.5, fontweight="bold")
    ax.text(x + w / 2, y - 0.12, sub, ha="center", va="top", color=DIM, fontsize=8.6, linespacing=1.3)
    if i < n - 1:
        ax.annotate("", xy=(x + w + gap - 0.03, y + h / 2), xytext=(x + w + 0.03, y + h / 2), arrowprops=dict(arrowstyle="-|>", color=FG, lw=1.2))
# the fallback: filter fails -> template
fx = 0.2 + 3 * (w + gap) + w / 2
ax.annotate("", xy=(fx, 0.5), xytext=(fx, 0.85), arrowprops=dict(arrowstyle="-|>", color="#E8A598", lw=1.2))
ax.text(fx, 0.42, "a note that fails the filter is replaced by a template\nand the trace records why", ha="center", va="top", color="#E8A598", fontsize=8.8, linespacing=1.3)
ax.text(0.2, 2.98, "the model restates the evidence: it cannot alter the evidence, the thresholds or the release decision", color=ACC, fontsize=10, va="top")
save(fig, os.path.join(os.path.dirname(os.path.abspath(__file__)), "slide12_ai_workflow.png"))
