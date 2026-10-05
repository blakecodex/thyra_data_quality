"""the demo as a subprocess, the way it runs in the room and in ci."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_the_demo_ships_the_clean_release_and_holds_the_seeded_one(tmp_path):
    out = tmp_path / "demo"
    proc = subprocess.run([sys.executable, "-m", "thyra.demo", "--out", str(out)], cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    assert "10/10 passed -> exit 0" in proc.stdout
    assert "exit 2 (release held)" in proc.stdout
    clean = json.loads((out / "clean" / "gate_report.json").read_text())
    seeded = json.loads((out / "seeded" / "gate_report.json").read_text())
    assert clean["exit_code"] == 0 and seeded["exit_code"] == 2
    assert (out / "seeded" / "report.md").exists()


@pytest.mark.parametrize("args, code", [([], 0), (["--inject", "hour_shift"], 2), (["--inject", "no_such_defect"], 1)])
def test_the_gate_exit_codes(tmp_path, args, code):
    proc = subprocess.run([sys.executable, "-m", "thyra.gate", "--quiet", "--out", str(tmp_path), *args], cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert proc.returncode == code, proc.stderr[-500:]
