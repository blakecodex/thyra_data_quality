"""slide 11: the gate table from a real run on the snapshot, rendered as an image.

run from the repository root: python diagrams/slide11_gate_table.py [path/to/gate_report.json]
without an argument it runs the demo's seeded scenario through the gate first.
"""
import json, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _style import canvas, save, BG, FG, DIM, ACC

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = os.path.join(REPO, "out", "figures", "seeded")
if len(sys.argv) > 1:
    report = json.load(open(sys.argv[1]))
else:
    subprocess.run([sys.executable, "-m", "thyra.gate", "--inject", "hour_shift,conflict,skew", "--quiet", "--out", out], cwd=REPO, check=False)
    report = json.load(open(os.path.join(out, "gate_report.json")))

rows = report["checks"]
fig, ax = canvas(9.0, 0.42 * (len(rows) + 3))
y = 0.42 * (len(rows) + 2)
def thr(r):
    t = r["threshold"]
    return f"within [{t[0]}, {t[1]}]" if r["op"] == "within" else f"{r['op']} {t}"
def val(v):
    return f"{v:.4f}" if isinstance(v, float) else str(v)
ax.text(0.2, y, "check", color=FG, fontsize=10, fontweight="bold", family="monospace")
ax.text(4.6, y, "value", color=FG, fontsize=10, fontweight="bold", family="monospace")
ax.text(5.9, y, "threshold", color=FG, fontsize=10, fontweight="bold", family="monospace")
ax.text(8.0, y, "result", color=FG, fontsize=10, fontweight="bold", family="monospace")
for r in rows:
    y -= 0.42
    c = "#E8A598" if not r["passed"] else DIM
    ax.text(0.2, y, r["check"], color=c, fontsize=10, family="monospace")
    ax.text(4.6, y, val(r["value"]), color=c, fontsize=10, family="monospace")
    ax.text(5.9, y, thr(r), color=c, fontsize=10, family="monospace")
    ax.text(8.0, y, "FAIL" if not r["passed"] else "pass", color=c, fontsize=10, family="monospace", fontweight="bold" if not r["passed"] else "normal")
passed = sum(r["passed"] for r in rows)
y -= 0.5
ax.text(0.2, y, f"{passed}/{len(rows)} passed -> exit {report['exit_code']} ({'release held' if report['exit_code'] else 'the candidate may ship'})", color=FG, fontsize=10.5, family="monospace", fontweight="bold")
save(fig, os.path.join(REPO, "diagrams", "slide11_gate_table.png"))
