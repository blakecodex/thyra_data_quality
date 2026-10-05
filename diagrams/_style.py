"""shared look for the deck's python-generated figures: dark background, white ink, arial-compatible font."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BG, FG, DIM, ACC = "#14171D", "#FFFFFF", "#D0D4DB", "#8FA3BF"
plt.rcParams["font.family"] = ["Liberation Sans", "DejaVu Sans"]  # liberation sans is metric-compatible with arial


def canvas(w, h):
    fig, ax = plt.subplots(figsize=(w, h), dpi=200)
    fig.patch.set_facecolor(BG); ax.set_facecolor(BG); ax.set_xlim(0, w); ax.set_ylim(0, h); ax.axis("off")
    return fig, ax


def save(fig, path):
    fig.savefig(path, facecolor=BG, bbox_inches="tight", pad_inches=0.1)
    print("wrote", path)
