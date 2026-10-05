"""triage: from the gate's report to an incident note a person can file, with a model that drafts and never decides.

    python -m thyra.triage out                  read out/gate_report.json, draft, ask, file the note
    python -m thyra.triage out --model bedrock  draft with a model on bedrock when credentials exist; the template otherwise
    python -m thyra.triage out --batch          no questions: write the draft and the trace, for ci

the order of work is fixed. code computes the diagnosis: which checks failed, the most upstream
first, with the numbers from the report. a drafter turns the diagnosis into six plain lines; the
drafter is a template by default and a language model when asked for and available. a filter reads
the draft: every number in it must appear in the report, no sentence may move a threshold and no
sentence may make or reverse the release decision. a draft that fails the filter is replaced by the
template and the trace says why. a person approves, edits or rejects; the note exists only after
approval, and the trace records every step.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# the families in the order a defect travels: a wrong hour count upstream explains a regression downstream
UPSTREAM_ORDER = ["data_quality", "integrity", "reconciliation", "drift", "accuracy", "regression", "bias", "calibration"]

NEXT_STEP = {
    "data_quality": "open the publisher's file for the hub-days named above and compare the hour labels with the calendar",
    "integrity": "diff the two copies of the hub-day and ask the owner of the loader which one is right",
    "reconciliation": "compare the desk's hourly integration with the published hourly file for the hours that differ",
    "drift": "compare the gated features in the held-out window with the reference window and look for a unit or schema change in the feed",
    "accuracy": "keep the champion; review the challenger's features before the next candidate run",
    "regression": "keep the champion; review the challenger's serving path for the peak hours",
    "bias": "keep the champion; review the challenger per hub before the next candidate run",
    "calibration": "keep the champion; review the challenger's band on the held-out window",
}

DECISION_PHRASES = ["should ship", "can ship", "safe to ship", "may ship", "promote the", "approve the", "override", "ignore the", "waive", "bypass", "release it", "release the candidate", "ship it"]
THRESHOLD_PHRASES = ["raise the threshold", "lower the threshold", "change the threshold", "loosen", "relax the", "tighten the", "new threshold", "adjust the threshold"]
NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?%?(?![\w.])")


# ----------------------------------------------------------------------------- diagnosis, by code

def diagnose(report: dict) -> dict:
    checks = report["checks"]
    failed = [c for c in checks if not c["passed"]]
    failed.sort(key=lambda c: UPSTREAM_ORDER.index(c["family"]) if c["family"] in UPSTREAM_ORDER else len(UPSTREAM_ORDER))
    data = report.get("data", {})
    evidence = {}
    for c in failed:
        name = c["check"]
        if name == "hour_count_days_wrong":
            evidence[name] = data.get("wrong_days", [])
        elif name == "quarantine_rate":
            evidence[name] = data.get("quarantine_reasons", {})
        elif name == "duplicate_conflicts":
            evidence[name] = {"conflicting_keys": data.get("conflicting_keys")}
        elif name in ("reconcile_share_off", "reconcile_mean_abs"):
            evidence[name] = {"reconciled_hours": data.get("reconciled_hours"), "tolerance": data.get("reconcile_tolerance")}
        elif name == "peak_no_regression":
            seg = next((s for s in report["backtest"]["by_block"] if s["name"] == "peak"), None)
            evidence[name] = seg
        elif name == "hub_no_regression":
            worst = max(report["backtest"]["by_hub"], key=lambda s: s["lo"])
            evidence[name] = worst
        elif name == "overall_improvement":
            evidence[name] = report["backtest"]["overall"]
        elif name == "band_coverage":
            evidence[name] = {"coverage": report["backtest"]["coverage_challenger"]}
        elif name == "psi_max":
            evidence[name] = report["backtest"]["psi"]
    return {
        "decision": "held" if report["exit_code"] != 0 else "ship",
        "exit_code": report["exit_code"],
        "injected": report.get("injected", []),
        "failed": [{"check": c["check"], "family": c["family"], "value": c["value"], "op": c["op"], "threshold": c["threshold"], "why": c["reason"]} for c in failed],
        "root": failed[0]["check"] if failed else None,
        "downstream": [c["check"] for c in failed[1:]],
        "passed": [c["check"] for c in checks if c["passed"]],
        "evidence": evidence,
    }


# ----------------------------------------------------------------------------- drafters

def fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:.4f}" if abs(v) < 100 else f"{v:.1f}"
    if isinstance(v, list):
        return f"[{v[0]}, {v[1]}]"
    return str(v)


def draft_template(diag: dict) -> str:
    """six lines, in order: what happened, what failed first, what else failed, the evidence, the next step, who decides."""
    if not diag["failed"]:
        return "\n".join([
            "Incident note: none. The gate passed every check and returned exit code 0.",
            "No check failed, so there is no root cause to name.",
            "The release may proceed on the usual approval.",
        ])
    root = diag["failed"][0]
    others = diag["failed"][1:]
    lines = [f"Incident note: the gate held the release with exit code {diag['exit_code']}; {len(diag['failed'])} of {len(diag['failed']) + len(diag['passed'])} checks failed."]
    lines.append(f"The most upstream failure is {root['check']} ({root['family']}): value {fmt(root['value'])} against {root['op']} {fmt(root['threshold'])}.")
    if others:
        lines.append("Downstream of it: " + "; ".join(f"{o['check']} at {fmt(o['value'])} against {o['op']} {fmt(o['threshold'])}" for o in others) + ".")
    else:
        lines.append("No other check failed.")
    ev = diag["evidence"].get(root["check"])
    if isinstance(ev, list) and ev:
        lines.append("Evidence: " + "; ".join(f"{e.get('hub')} on {e.get('day')} shows {e.get('hours_seen')} hours against {e.get('hours_expected')} expected" for e in ev[:3]) + ".")
    elif isinstance(ev, dict) and ev:
        lines.append("Evidence: " + ", ".join(f"{k} {fmt(v)}" for k, v in ev.items() if not isinstance(v, (dict, list))) + ".")
    else:
        lines.append("Evidence: see the gate report for the values behind each check.")
    lines.append(f"Next step: {NEXT_STEP.get(root['family'], 'review the report with the check owner')}.")
    lines.append("The gate made the hold; a person decides what happens next, and this note changes none of the thresholds.")
    return "\n".join(lines)


def draft_bedrock(diag: dict, model_id: str) -> tuple[str | None, str]:
    """ask a model on bedrock for the six lines. returns (text, note); text is none when the call could not be made."""
    try:
        import boto3  # noqa: WPS433 (an optional dependency)
    except ImportError:
        return None, "boto3 is not installed"
    prompt = (
        "You write incident notes for a data quality gate. Write at most six short lines in plain words.\n"
        "Rules: use only numbers that appear in the JSON below, written the same way; do not suggest changing any threshold; "
        "do not recommend shipping, promoting, approving or overriding anything; the gate's decision stands and a person decides next steps.\n"
        "Order: what happened, the most upstream failure, what else failed, the evidence, the next step, who decides.\n\n"
        f"JSON:\n{json.dumps(diag, indent=1, default=str)}"
    )
    try:
        client = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1")))
        resp = client.converse(modelId=model_id, messages=[{"role": "user", "content": [{"text": prompt}]}], inferenceConfig={"maxTokens": 400, "temperature": 0.0})
        text = "".join(part.get("text", "") for part in resp["output"]["message"]["content"]).strip()
        return text, f"bedrock:{model_id}"
    except Exception as e:  # no credentials, no access to the model, no network: the template takes over
        return None, f"bedrock call failed: {type(e).__name__}: {e}"


# ----------------------------------------------------------------------------- the filter, by code

def allowed_numbers(report: dict) -> set[str]:
    """every number a note may use: everything numeric in the report, at the precisions the drafters print."""
    out: set[str] = set()

    def add(v):
        if isinstance(v, bool):
            return
        if isinstance(v, int):
            out.add(str(v))
        elif isinstance(v, float):
            for s in (f"{v:.4f}", f"{v:.3f}", f"{v:.2f}", f"{v:.1f}", f"{v:.0f}", f"{v:+.3f}", f"{v * 100:.1f}%", f"{v * 100:.0f}%", repr(v)):
                out.add(s.lstrip("+"))
        elif isinstance(v, str):
            for tok in NUMBER.findall(v):
                out.add(tok)
            for tok in re.findall(r"\d+", v):
                out.add(tok)
        elif isinstance(v, dict):
            for x in v.values():
                add(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                add(x)

    add(report)
    out.update({str(n) for n in range(0, 32)})  # counts of checks, hours, days: small integers a note needs
    return out


def check_draft(draft: str, report: dict, max_lines: int = 8) -> tuple[bool, list[str]]:
    reasons = []
    lines = [l for l in draft.splitlines() if l.strip()]
    if len(lines) > max_lines:
        reasons.append(f"{len(lines)} lines; the limit is {max_lines}")
    allowed = allowed_numbers(report)
    for tok in NUMBER.findall(draft):
        if tok not in allowed and tok.rstrip("%") not in allowed and tok.lstrip("-") not in allowed:
            reasons.append(f"number not in the report: {tok}")
    low = draft.lower()
    for phrase in THRESHOLD_PHRASES:
        if phrase in low:
            reasons.append(f"moves a threshold: '{phrase}'")
    for phrase in DECISION_PHRASES:
        if phrase in low:
            reasons.append(f"makes a release decision: '{phrase}'")
    return (not reasons), reasons


# ----------------------------------------------------------------------------- the run

def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def triage(out_dir: Path, model: str = "template", model_id: str | None = None) -> dict:
    report_path = out_dir / "gate_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    diag = diagnose(report)
    trace = {"report": str(report_path), "report_sha256": sha256_file(report_path), "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "diagnosis": diag, "steps": []}

    drafter = "template"
    text = None
    if model == "bedrock":
        mid = model_id or os.environ.get("THYRA_BEDROCK_MODEL", "us.anthropic.claude-3-5-haiku-20241022-v1:0")
        text, note = draft_bedrock(diag, mid)
        trace["steps"].append({"step": "draft", "drafter": "bedrock", "model": mid, "result": "ok" if text else note})
        if text:
            drafter = note
    if text is None:
        text = draft_template(diag)
        trace["steps"].append({"step": "draft", "drafter": "template", "result": "ok"})

    ok, reasons = check_draft(text, report)
    trace["steps"].append({"step": "filter", "drafter": drafter, "passed": ok, "reasons": reasons})
    if not ok:
        text = draft_template(diag)
        drafter = "template (fallback)"
        ok2, reasons2 = check_draft(text, report)
        trace["steps"].append({"step": "filter", "drafter": drafter, "passed": ok2, "reasons": reasons2})
        if not ok2:
            raise RuntimeError(f"the template itself failed the filter: {reasons2}")
    trace["drafter"] = drafter
    trace["draft"] = text
    return trace


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
    ap = argparse.ArgumentParser(prog="thyra.triage", description="draft an incident note from a gate report; a person approves it")
    ap.add_argument("out", nargs="?", default="out", help="the folder holding gate_report.json")
    ap.add_argument("--model", choices=["template", "bedrock"], default="template")
    ap.add_argument("--model-id", default=None)
    ap.add_argument("--batch", action="store_true", help="write the draft and the trace without asking; no note is filed")
    ap.add_argument("--approve-draft", action="store_true", help="file the draft in incident_note.draft.md as edited, after the filter reads it again")
    args = ap.parse_args(argv)
    out = Path(args.out)
    draft_path, note_path, trace_path = out / "incident_note.draft.md", out / "incident_note.md", out / "triage_trace.json"

    if args.approve_draft:
        report = json.loads((out / "gate_report.json").read_text(encoding="utf-8"))
        text = draft_path.read_text(encoding="utf-8")
        ok, reasons = check_draft(text, report)
        trace = json.loads(trace_path.read_text(encoding="utf-8")) if trace_path.exists() else {"steps": []}
        trace["steps"].append({"step": "filter (edited draft)", "passed": ok, "reasons": reasons})
        if not ok:
            print("the edited draft fails the filter:\n  " + "\n  ".join(reasons))
            trace_path.write_text(json.dumps(trace, indent=2), encoding="utf-8")
            return 2
        note_path.write_text(text, encoding="utf-8")
        trace.update({"decision": "approved (edited)", "approved_by": getpass.getuser(), "decided_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        trace_path.write_text(json.dumps(trace, indent=2), encoding="utf-8")
        print(f"filed {note_path}")
        return 0

    trace = triage(out, args.model, args.model_id)
    draft_path.write_text(trace["draft"], encoding="utf-8")
    print(f"draft by {trace['drafter']}; filter passed; most upstream failure: {trace['diagnosis']['root'] or 'none'}\n")
    print(trace["draft"])
    print()
    if args.batch:
        trace["decision"] = "batch: draft written, no note filed"
        trace_path.write_text(json.dumps(trace, indent=2, default=str), encoding="utf-8")
        print(f"draft at {draft_path}; trace at {trace_path}")
        return 0
    answer = input("approve (a), edit (e) or reject (r)? ").strip().lower()
    if answer == "a":
        note_path.write_text(trace["draft"], encoding="utf-8")
        trace.update({"decision": "approved", "approved_by": getpass.getuser()})
        print(f"filed {note_path}")
    elif answer == "e":
        trace["decision"] = "sent back for edits"
        print(f"edit {draft_path}, then run: python -m thyra.triage {out} --approve-draft")
    else:
        trace["decision"] = "rejected"
        print("rejected; no note filed")
    trace["decided_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    trace_path.write_text(json.dumps(trace, indent=2, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
