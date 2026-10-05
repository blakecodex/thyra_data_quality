"""triage: code diagnoses, the template drafts, the filter reads every number and a person decides."""

import json
import subprocess
import sys
from pathlib import Path

from thyra.gate import build_run, load_suite, run_gate, write_outputs
from thyra.triage import check_draft, diagnose, draft_template, triage

ROOT = Path(__file__).resolve().parent.parent


def _report(tmp_path, injected):
    suite = load_suite()
    run = build_run(7, injected, suite)
    code, results = run_gate(run, suite)
    write_outputs(tmp_path, run, results, code, suite)
    return json.loads((tmp_path / "gate_report.json").read_text(encoding="utf-8"))


def test_the_diagnosis_names_the_most_upstream_failure_first(tmp_path):
    report = _report(tmp_path, ["hour_shift", "conflict", "skew"])
    diag = diagnose(report)
    assert diag["decision"] == "held"
    assert diag["root"] == "hour_count_days_wrong"
    assert diag["downstream"][0] == "duplicate_conflicts"
    assert diag["evidence"]["hour_count_days_wrong"][0]["hub"] == "N.Y.C."


def test_the_template_passes_the_filter_on_every_demo_report(tmp_path):
    for injected in ([], ["hour_shift", "conflict", "skew"], ["load_units"]):
        report = _report(tmp_path / "-".join(injected or ["clean"]), injected)
        text = draft_template(diagnose(report))
        ok, reasons = check_draft(text, report)
        assert ok, reasons
        assert len([l for l in text.splitlines() if l.strip()]) <= 8


def test_the_filter_rejects_a_number_that_is_not_in_the_report(tmp_path):
    report = _report(tmp_path, ["conflict"])
    ok, reasons = check_draft("The gate held the release; 37 hub-days were wrong and the loss was 12.5 percent.", report)
    assert not ok and any("37" in r for r in reasons)


def test_the_filter_rejects_a_release_decision_and_a_moved_threshold(tmp_path):
    report = _report(tmp_path, ["conflict"])
    ok, reasons = check_draft("One conflict was found. The candidate should ship anyway.", report)
    assert not ok and any("decision" in r for r in reasons)
    ok, reasons = check_draft("One conflict was found. Lower the threshold to 1 and rerun.", report)
    assert not ok and any("threshold" in r for r in reasons)


def test_a_bad_model_draft_falls_back_to_the_template_and_the_trace_says_why(tmp_path, monkeypatch):
    import thyra.triage as t
    report = _report(tmp_path, ["conflict"])
    monkeypatch.setattr(t, "draft_bedrock", lambda diag, model_id: ("Ship it: the conflict is only 1 key and the threshold should be 2.", "bedrock:fake"))
    trace = triage(tmp_path, model="bedrock", model_id="fake")
    assert trace["drafter"] == "template (fallback)"
    steps = [s for s in trace["steps"] if s["step"] == "filter"]
    assert steps[0]["passed"] is False and steps[1]["passed"] is True


def test_batch_mode_writes_the_draft_and_the_trace_but_no_note(tmp_path):
    _report(tmp_path, ["hour_shift"])
    proc = subprocess.run([sys.executable, "-m", "thyra.triage", str(tmp_path), "--batch"], cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr[-800:]
    assert (tmp_path / "incident_note.draft.md").exists() and (tmp_path / "triage_trace.json").exists()
    assert not (tmp_path / "incident_note.md").exists()
    assert "hour_count_days_wrong" in proc.stdout
