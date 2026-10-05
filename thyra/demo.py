"""the demo: the gate on a clean release, then on a release with three seeded defects.

about ten seconds end to end. the first run passes every check and exits 0. the second carries
two data defects, the 25-hour day labelled one hour early and a file loaded twice with one row
changed, plus a serving skew in the candidate model: a feature the training code computed and
the serving path never did. the gate holds with exit 2 and names each check that failed.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .evaluate import render
from .gate import EXIT_HOLD, EXIT_SHIP, build_run, format_data, format_table, load_suite, run_gate, write_outputs

SEEDED = ["hour_shift", "conflict", "skew"]


def say(text: str) -> None:
    print(f"\n== {text}")


def main(argv: list[str] | None = None) -> int:
    # windows consoles are not always utf-8; the tables use a middle dot and should not crash for it
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
    ap = argparse.ArgumentParser(prog="thyra.demo")
    ap.add_argument("--out", default="out/demo")
    ap.add_argument("--suite", default=None)
    ap.add_argument("--snapshot", default=None)
    args = ap.parse_args(argv)
    suite = load_suite(args.suite) if args.suite else load_suite()
    seed = int(suite.get("seed", 7))
    t0 = time.time()

    say("1. a clean release: eleven zones, the snapshot as published")
    clean = build_run(seed, [], suite, args.snapshot)
    code_clean, res_clean = run_gate(clean, suite)
    write_outputs(Path(args.out) / "clean", clean, res_clean, code_clean, suite)
    print(format_data(clean))
    print()
    print(render(clean.report, suite.get("drift_features")))
    print()
    print(format_table(res_clean, code_clean))

    say("2. the same release with three seeded defects: the 25-hour day labelled one hour early, a file loaded twice with one row changed and a feature missing at serving time")
    seeded = build_run(seed, SEEDED, suite, args.snapshot)
    code_seeded, res_seeded = run_gate(seeded, suite)
    write_outputs(Path(args.out) / "seeded", seeded, res_seeded, code_seeded, suite)
    print(format_data(seeded))
    print()
    print(render(seeded.report, suite.get("drift_features")))
    print()
    print(format_table(res_seeded, code_seeded))

    print(f"\ndone in {time.time() - t0:.0f}s. the clean release ships; the seeded release is held. reports under {args.out}/")
    ok = code_clean == EXIT_SHIP and code_seeded == EXIT_HOLD
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
