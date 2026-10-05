"""slide 4: the platform, and the quality control at each handoff.

run from the repository root: python diagrams/slide04_platform.py  -> diagrams/slide04_platform.png
plain matplotlib, dark background to match the deck. no data, just the shape of the system.
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

BG, FG, DIM, ACC = "#14171D", "#FFFFFF", "#D0D4DB", "#8FA3BF"
plt.rcParams["font.family"] = ["Liberation Sans", "Arial", "DejaVu Sans"]  # liberation sans is metric-compatible with arial

stages = [
    ("Source feeds", "day-ahead prices\n5-min real-time prices\nload, weather"),
    ("S3", "landing"),
    ("Snowflake", "warehouse"),
    ("Hub-hour\nfeatures", "feature generation"),
    ("Forecast\nmodels", "one per hub\nMLflow runs"),
    ("FastAPI\nservice", "forecast + band"),
    ("Client desk", "trading and\nrisk analysis"),
]
checks = [
    None,
    "data contract:\nfields, units, ranges,\ntimestamps, reason codes",
    "completeness per hub-day\npreliminary vs verified\nrerun-safe loads",
    "feature tests:\ntime-aligned,\nrepeatable",
    "promotion gate:\ncandidate vs champion\nby hub and hour block",
    "monitoring:\ninput drift,\nerror vs backtest band",
    None,
]

fig, ax = plt.subplots(figsize=(13.33, 4.0), dpi=200)
fig.patch.set_facecolor(BG); ax.set_facecolor(BG); ax.set_xlim(0, 13.33); ax.set_ylim(0, 4.0); ax.axis("off")

n = len(stages); w, h, gap = 1.55, 1.15, (13.33 - 0.5 - n * 1.55) / (n - 1)
y = 2.4
for i, (name, sub) in enumerate(stages):
    x = 0.25 + i * (w + gap)
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.06", fc=BG, ec=FG, lw=1.3))
    ax.text(x + w / 2, y + h - 0.32, name, ha="center", va="center", color=FG, fontsize=10.5, fontweight="bold")
    ax.text(x + w / 2, y + 0.32, sub, ha="center", va="center", color=DIM, fontsize=7.8)
    if i < n - 1:
        ax.annotate("", xy=(x + w + gap - 0.03, y + h / 2), xytext=(x + w + 0.03, y + h / 2), arrowprops=dict(arrowstyle="-|>", color=FG, lw=1.2))
    if checks[i]:
        ax.annotate("", xy=(x + w / 2, y - 0.9), xytext=(x + w / 2, y - 0.05), arrowprops=dict(arrowstyle="-|>", color=ACC, lw=1.2))
        ax.text(x + w / 2, y - 1.0, checks[i], ha="center", va="top", color=ACC, fontsize=8.2, linespacing=1.3)

ax.text(0.25, 0.12, "A quality control at each handoff. MLflow holds every run and approval; GitLab CI runs the tests and the gate.", color=DIM, fontsize=9.5, va="bottom")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "slide04_platform.png")
fig.savefig(OUT, facecolor=BG, bbox_inches="tight", pad_inches=0.1)
print("wrote", OUT)
