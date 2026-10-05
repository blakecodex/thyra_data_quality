"""the release gate: run the pipeline on the snapshot, score the candidate, read every check, return an exit code.

exit 0 means the candidate may ship. exit 2 means the release is held, and the table says why.
exit 1 means the gate itself could not run, which also holds, because a gate that cannot run is
not evidence that all is well.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yaml

from . import feeds
from .contract import validate
from .evaluate import Report, backtest, render
from .features import build_features
from .model import Ridge, fit_challenger, fit_champion
from .reconcile import apply_revisions, interval_counts, revision_summary, split_duplicates

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SUITE = ROOT / "gate.yaml"
DEFAULT_OUT = "out"

EXIT_SHIP, EXIT_CANNOT_RUN, EXIT_HOLD = 0, 1, 2

# the seeded defects the gate exists to catch. each names what it touches: the published rows,
# the forecast feed or the model layer; and each is aimed at one hub-day or one window.
INJECTIONS = {
    "hour_shift": ("rows", lambda rows: feeds.shift_hour(rows, "N.Y.C.", date(2025, 11, 2))),          # the 25-hour day, labelled one hour early
    "conflict": ("rows", lambda rows: feeds.retry_with_conflict(rows, "LONGIL", date(2025, 12, 15))),  # a file loaded twice with one row changed
    "retry": ("rows", lambda rows: feeds.retry(rows, "WEST", date(2025, 11, 20))),                     # a file loaded twice, identical; nothing should fail
    "unit_slip": ("rows", lambda rows: feeds.unit_slip(rows, "CAPITL", date(2025, 10, 10))),           # one hub-day published in $/kwh
    "missing_hour": ("rows", lambda rows: feeds.missing_hour(rows, "CENTRL", date(2026, 1, 20), 7)),   # one hour never arrives
    "fake_hour": ("rows", lambda rows: feeds.fake_hour(rows, "NORTH", date(2026, 1, 5))),              # an hour the day does not have
    "load_units": ("forecasts", None),                                                                 # the load forecast feed switches units in the held-out window
    "skew": ("model", None),                                                                           # a feature missing at serving time
}


@dataclass
class Run:
    seed: int
    injected: list[str]
    published: int
    accepted: pd.DataFrame
    quarantined: pd.DataFrame
    retries_dropped: int
    conflicts: pd.DataFrame
    counts: pd.DataFrame
    revisions: pd.DataFrame
    final: pd.DataFrame
    revision: pd.DataFrame
    train: pd.DataFrame
    test: pd.DataFrame
    after: pd.DataFrame          # the days after the gate's window: what production saw once the release was out
    champion: Ridge
    challenger: Ridge
    report: Report
    data: dict = field(default_factory=dict)


def load_suite(path: str | Path = DEFAULT_SUITE) -> dict:
    suite = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    for name in ("split_day", "reference_days", "checks"):
        if name not in suite:
            raise ValueError(f"suite is missing '{name}'")
    return suite


_SNAPSHOT_CACHE: dict[str, feeds.Published] = {}


def published(snapshot: str | Path | None = None) -> feeds.Published:
    """the snapshot, read once per process."""
    key = str(Path(snapshot) if snapshot else feeds.SNAPSHOT)
    if key not in _SNAPSHOT_CACHE:
        _SNAPSHOT_CACHE[key] = feeds.load_snapshot(key)
    return _SNAPSHOT_CACHE[key]


def build_run(seed: int, injected: list[str], suite: dict, snapshot: str | Path | None = None) -> Run:
    pub = published(snapshot)
    rows, forecasts = list(pub.rows), pub.forecasts
    split = pub.start + timedelta(days=int(suite["split_day"]))
    tolerance = float(suite.get("reconcile_tolerance", 2.0))
    for name in injected:
        if name not in INJECTIONS:
            raise ValueError(f"unknown injection '{name}'; choose from {', '.join(INJECTIONS)}")
        target, fn = INJECTIONS[name]
        if target == "rows":
            rows = fn(rows)
        elif name == "load_units":
            forecasts = feeds.forecast_unit_change(forecasts, split)
    accepted, quarantined = validate(rows)
    clean, retries, conflicts = split_duplicates(accepted)
    counts = interval_counts(clean)
    revisions = pd.DataFrame(pub.revisions)
    final = apply_revisions(clean, revisions)
    revision = revision_summary(clean, final, tolerance)
    df = build_features(final, clean, forecasts)
    monitor_from = pub.start + timedelta(days=int(suite.get("monitor_from_day", 10**6)))
    train = df[df["day"] < split]
    test = df[(df["day"] >= split) & (df["day"] < monitor_from)]
    after = df[df["day"] >= monitor_from]
    if train.empty or test.empty:
        raise ValueError(f"the split on {split} leaves an empty window: train {len(train)} rows, test {len(test)} rows")
    reference = train[train["day"] >= split - timedelta(days=int(suite["reference_days"]))]
    champion = fit_champion(train)
    challenger = fit_challenger(train, serving_skew="skew" in injected)
    report = backtest(champion, challenger, reference, test, seed=seed)
    both = final.merge(clean, on=["hub", "day", "hour"], suffixes=("_final", "_prelim")).dropna(subset=["price_rt_final", "price_rt_prelim"])
    delta = (both["price_rt_final"] - both["price_rt_prelim"]).abs()
    data = {
        "window": {"start": pub.start.isoformat(), "end": pub.end.isoformat(), "split": split.isoformat(), "monitor_from": monitor_from.isoformat() if not after.empty else None},
        "published_rows": len(rows),
        "accepted_rows": int(len(accepted)),
        "quarantined_rows": int(len(quarantined)),
        "quarantine_reasons": quarantined["reason"].value_counts().to_dict() if len(quarantined) else {},
        "retries_dropped": int(retries),
        "conflicting_keys": int(conflicts[["hub", "day", "hour"]].drop_duplicates().shape[0]) if len(conflicts) else 0,
        "hub_days": int(len(counts)),
        "hub_days_wrong": int((~counts["ok"]).sum()),
        "wrong_days": counts[~counts["ok"]][["hub", "day", "hours_seen", "hours_expected"]].astype(str).to_dict("records"),
        "reconcile_tolerance": tolerance,
        "reconciled_hours": int(len(delta)),
        "reconcile_share_off": float((delta > tolerance).mean()) if len(delta) else 0.0,
        "reconcile_mean_abs": float(delta.mean()) if len(delta) else 0.0,
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "after_rows": int(len(after)),
    }
    return Run(seed, list(injected), len(rows), accepted, quarantined, retries, conflicts, counts, revisions, final, revision, train, test, after, champion, challenger, report, data)


def values_for(run: Run, suite: dict) -> dict[str, float]:
    """the one number each check reads, computed from the run."""
    r = run.report
    peak = next(s for s in r.by_block if s.name == "peak")
    gated = [f for f in suite.get("drift_features", list(r.psi)) if f in r.psi]
    return {
        "quarantine_rate": run.data["quarantined_rows"] / max(run.data["published_rows"], 1),
        "hour_count_days_wrong": run.data["hub_days_wrong"],
        "duplicate_conflicts": run.data["conflicting_keys"],
        "reconcile_share_off": run.data["reconcile_share_off"],
        "reconcile_mean_abs": run.data["reconcile_mean_abs"],
        "overall_improvement": r.overall.hi,
        "peak_no_regression": peak.lo,
        "hub_no_regression": max(s.lo for s in r.by_hub),
        "band_coverage": r.coverage_challenger,
        "psi_max": max(r.psi[f] for f in gated) if gated else float("nan"),
    }


def compare(value, op: str, threshold) -> bool:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return False
    if op == "<=":
        return value <= threshold
    if op == "<":
        return value < threshold
    if op == "==":
        return value == threshold
    if op == "within":
        lo, hi = threshold
        return lo <= value <= hi
    raise ValueError(f"unknown op {op}")


def run_gate(run: Run, suite: dict) -> tuple[int, list[dict]]:
    values = values_for(run, suite)
    results = []
    for name, spec in suite["checks"].items():
        if name not in values:
            results.append({"check": name, "family": spec.get("family", ""), "value": None, "op": spec["op"], "threshold": spec["threshold"], "passed": False, "reason": "no value computed"})
            continue
        v = values[name]
        ok = compare(v, spec["op"], spec["threshold"])
        results.append({"check": name, "family": spec.get("family", ""), "value": v, "op": spec["op"], "threshold": spec["threshold"], "passed": bool(ok), "reason": "" if ok else spec.get("why", "")})
    code = EXIT_SHIP if all(r["passed"] for r in results) else EXIT_HOLD
    return code, results


def format_table(results: list[dict], code: int) -> str:
    def fmt(v):
        if v is None:
            return "n/a"
        if isinstance(v, float):
            return f"{v:.4f}" if abs(v) < 100 else f"{v:.1f}"
        return str(v)
    def thr(r):
        t = r["threshold"]
        return f"within [{t[0]}, {t[1]}]" if r["op"] == "within" else f"{r['op']} {t}"
    lines = [f"  {'check':24s} {'value':>10s}   {'threshold':18s} result"]
    for r in results:
        lines.append(f"  {r['check']:24s} {fmt(r['value']):>10s}   {thr(r):18s} {'pass' if r['passed'] else 'FAIL'}")
    passed = sum(r["passed"] for r in results)
    verdict = {EXIT_SHIP: "exit 0 (the candidate may ship)", EXIT_HOLD: "exit 2 (release held)"}[code]
    lines.append(f"  {passed}/{len(results)} passed -> {verdict}")
    return "\n".join(lines)


def format_data(run: Run) -> str:
    d = run.data
    lines = [
        f"window             {d['window']['start']} to {d['window']['end']}; held out from {d['window']['split']}" + (f"; production from {d['window']['monitor_from']}" if d['window'].get('monitor_from') else ""),
        f"data at the door   published {d['published_rows']:,} rows · accepted {d['accepted_rows']:,} · quarantined {d['quarantined_rows']} {d['quarantine_reasons'] if d['quarantine_reasons'] else ''}",
        f"in the warehouse   retries dropped {d['retries_dropped']} · conflicting keys {d['conflicting_keys']} · hub-days {d['hub_days']} · wrong hour counts {d['hub_days_wrong']} {d['wrong_days'] if d['wrong_days'] else ''}",
        f"reconciliation     {d['reconcile_share_off']:.1%} of {d['reconciled_hours']:,} hours differ by more than {d['reconcile_tolerance']:.0f} $/MWh between the desk's hourly integration and the published hourly price; mean |difference| {d['reconcile_mean_abs']:.2f} $/MWh",
        f"windows            train {d['train_rows']:,} hub-hours · held out {d['test_rows']:,}" + (f" · production {d['after_rows']:,}" if d.get('after_rows') else ""),
    ]
    return "\n".join(lines)


def write_outputs(out: Path, run: Run, results: list[dict], code: int, suite: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    payload = {"suite": suite.get("suite", ""), "seed": run.seed, "injected": run.injected, "exit_code": code, "checks": results, "data": run.data, "backtest": run.report.to_dict()}
    (out / "gate_report.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    md = ["# thyra gate report", "", f"injected: {', '.join(run.injected) or 'none'}", "", "```", format_data(run), "", render(run.report, suite.get("drift_features")), "", format_table(results, code), "```", ""]
    (out / "report.md").write_text("\n".join(md), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    # windows consoles are not always utf-8; the tables use a middle dot and should not crash for it
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
    ap = argparse.ArgumentParser(prog="thyra.gate", description="run the pipeline and the release gate on the snapshot")
    ap.add_argument("--seed", type=int, default=None, help="the bootstrap seed; default from gate.yaml")
    ap.add_argument("--inject", default="", help="comma-separated seeded defects: " + ", ".join(INJECTIONS))
    ap.add_argument("--suite", default=str(DEFAULT_SUITE))
    ap.add_argument("--snapshot", default=None, help="a different snapshot folder; default data/snapshot")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    try:
        suite = load_suite(args.suite)
        seed = args.seed if args.seed is not None else int(suite.get("seed", 7))
        injected = [s.strip() for s in args.inject.split(",") if s.strip()]
        run = build_run(seed, injected, suite, args.snapshot)
        code, results = run_gate(run, suite)
        write_outputs(Path(args.out), run, results, code, suite)
    except Exception as e:  # the gate could not run; that holds the release too
        print(f"gate could not run: {e}", file=sys.stderr)
        return EXIT_CANNOT_RUN
    if not args.quiet:
        print(format_data(run))
        print()
        print(render(run.report, suite.get("drift_features")))
        print()
        print(format_table(results, code))
    return code


if __name__ == "__main__":
    sys.exit(main())
