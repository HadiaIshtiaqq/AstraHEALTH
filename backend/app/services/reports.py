"""Mission health report: assembly, CSV export and printable HTML export."""
from __future__ import annotations

import csv
import html
import io
from datetime import timedelta

from app.core.config import APP_VERSION
from app.db.database import Database, dumps, iso, loads, new_id, parse_iso, utcnow
from app.domain.metrics import METRICS
from app.ml.isolation_forest import MODEL_NAME, MODEL_VERSION
from app.ml.stats import robust_summary
from app.rag.index import knowledge_index
from app.safety.rules import get_ruleset
from app.services import repository as repo

DISCLAIMER = (
    "PROTOTYPE — NOT A MEDICAL DEVICE. ASTRAHEALTH AI is a hackathon research prototype. It does not provide a "
    "diagnosis and must not be used to make real flight or clinical decisions. "
    "Severity rules are demonstration placeholders that have not been clinically validated."
)

def build_report(db: Database, profile_id: str, start: str | None, end: str | None) -> dict:
    profile = repo.get_profile(db, profile_id)
    if profile is None:
        raise LookupError("Profile not found")
    end_dt = parse_iso(end) if end else utcnow()
    start_dt = parse_iso(start) if start else end_dt - timedelta(days=7)
    if start_dt > end_dt:
        raise ValueError("Report start must be before end")
    observations = repo.get_observations(db, profile_id, start=start_dt, end=end_dt)
    runs = db.query("SELECT run_id FROM analysis_runs WHERE profile_id = ? AND started_at BETWEEN ? AND ? "
                    "AND status = 'completed' ORDER BY started_at", (profile_id, iso(start_dt), iso(end_dt + timedelta(minutes=5))))
    latest = repo.get_run(db, runs[-1]["run_id"]) if runs else None
    alerts = [a for a in repo.get_alerts(db, profile_id) if start_dt <= parse_iso(a["created_at"]) <= end_dt + timedelta(minutes=5)]

    summaries = []
    for code, metric in METRICS.items():
        vals = [o["normalized_value"] for o in observations
                if o["metric_code"] == code and o["quality_status"] == "valid" and o["normalized_value"] is not None]
        if vals:
            s = robust_summary(vals, code)
            summaries.append({"metric_code": code, "label": metric.label, "unit": metric.normalized_unit,
                              "n": s["n"], "min": s["min"], "median": s["median"], "max": s["max"]})
        else:
            if code in ("heart_rate", "sleep_duration", "mood", "stress", "fatigue", "exercise_duration", "fluid_intake"):
                summaries.append({"metric_code": code, "label": metric.label, "unit": metric.normalized_unit,
                                  "n": 0, "min": None, "median": None, "max": None, "missing": True})

    findings = latest["assessment"].get("findings", []) if latest else []
    cited = {}
    for f in findings:
        for r in f.get("knowledge_references", []):
            cited[r["document_id"]] = {"document_id": r["document_id"], "title": r["title"], "publisher": r["publisher"],
                                       "version": r.get("version"), "publication_date": r.get("publication_date")}
    ruleset = get_ruleset()
    report = {
        "report_id": new_id("rpt"),
        "generated_at": iso(utcnow()),
        "disclaimer": DISCLAIMER + (" This profile and its readings are SYNTHETIC (generated demo data, not a real person)."
                                    if profile["is_synthetic"] else " This profile holds data entered by its user."),
        "is_synthetic": profile["is_synthetic"],
        "header": {
            "profile_alias": profile["display_name"], "profile_id": profile_id, "role": profile.get("role"),
            "mission": profile["mission_name"], "mission_day": profile["mission_day"] if profile["mission_day"] is not None else "—", "environment": profile["environment"],
            "window_start": iso(start_dt), "window_end": iso(end_dt),
        },
        "versions": {"app": APP_VERSION, "ruleset": ruleset.version, "ruleset_status": ruleset.status,
                     "ruleset_checksum": ruleset.checksum, "anomaly_model": f"{MODEL_NAME} {MODEL_VERSION}",
                     "knowledge_index": knowledge_index.status().get("index_version"),
                     "latest_run_agent_versions": latest["agent_versions"] if latest else {}},
        "latest_assessment": {k: v for k, v in (latest["assessment"] if latest else {}).items() if k != "findings"} or None,
        "latest_run_id": latest["run_id"] if latest else None,
        "latest_run_completed_at": latest["completed_at"] if latest else None,
        "findings": [{k: f[k] for k in ("code", "summary", "severity", "agent_id", "rule_ids", "evidence_observation_ids",
                                        "limitations", "next_steps", "evidence_status", "statement_type")}
                     | {"references": [{"chunk_id": r["chunk_id"], "title": r["title"], "section": r["section"]}
                                       for r in f.get("knowledge_references", [])]}
                     for f in findings if f["severity"] != "INFO" or f["code"] in ("BASELINE_UNAVAILABLE", "MISSING_CORE_MEASUREMENTS", "AGENT_FAILED")],
        "alerts": [{k: a[k] for k in ("alert_id", "severity", "title", "reason", "next_step", "state", "created_at",
                                      "acknowledged_at", "rule_ids", "evidence_ids")} for a in alerts],
        "unresolved_alerts": sum(1 for a in alerts if a["state"] == "open" and a["severity"] in ("REVIEW", "URGENT")),
        "metric_summaries": summaries,
        "measurements": [{
            "observation_id": o["observation_id"], "metric_code": o["metric_code"],
            "label": METRICS[o["metric_code"]].label if o["metric_code"] in METRICS else o["metric_code"],
            "value": o["value"] if o["value"] is not None else o["value_text"], "unit": o["unit"],
            "normalized_value": o["normalized_value"], "normalized_unit": o["normalized_unit"],
            "measured_at": o["measured_at"], "recorded_at": o["recorded_at"], "source": o["source"],
            "context": o["context"], "quality_status": o["quality_status"], "is_synthetic": o["is_synthetic"],
        } for o in observations],
        "analysis_runs": len(runs),
        "sources": list(cited.values()),
    }
    with db.transaction() as conn:
        conn.execute("INSERT INTO reports VALUES (?,?,?,?,?,?)", (report["report_id"], profile_id, iso(start_dt), iso(end_dt),
                                                                   report["generated_at"], dumps(report)))
    repo.audit(db, "report.generated", report["report_id"], actor_role="crew", measurements=len(observations))
    return report


def get_report(db: Database, report_id: str) -> dict | None:
    row = db.one("SELECT report_json FROM reports WHERE report_id = ?", (report_id,))
    return loads(row["report_json"]) if row else None


def to_csv(report: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["# ASTRAHEALTH AI mission health report", report["report_id"]])
    w.writerow(["# " + report["disclaimer"]])
    h = report["header"]
    w.writerow(["# profile", h["profile_alias"], "mission", h["mission"], "mission_day", h["mission_day"]])
    w.writerow(["# window", h["window_start"], h["window_end"], "generated_at", report["generated_at"]])
    w.writerow(["# versions", f"app {report['versions']['app']}", f"ruleset {report['versions']['ruleset']}",
                report["versions"]["anomaly_model"]])
    w.writerow([])
    cols = ["observation_id", "metric_code", "label", "value", "unit", "normalized_value", "normalized_unit",
            "measured_at", "recorded_at", "source", "context", "quality_status", "is_synthetic"]
    w.writerow(cols)
    for m in report["measurements"]:
        w.writerow([m[c] for c in cols])
    w.writerow([])
    w.writerow(["alert_id", "severity", "title", "reason", "next_step", "state", "created_at", "rule_ids"])
    for a in report["alerts"]:
        w.writerow([a["alert_id"], a["severity"], a["title"], a["reason"], a["next_step"], a["state"], a["created_at"],
                    ";".join(a["rule_ids"])])
    return buf.getvalue()


def to_html(report: dict) -> str:
    e = html.escape
    h = report["header"]
    a = report.get("latest_assessment") or {}
    sev_color = {"URGENT": "#B54747", "REVIEW": "#9A5B00", "MONITOR": "#8A6A00", "INFO": "#4A5A70"}

    def rows(items, cols):
        return "".join("<tr>" + "".join(f"<td>{e(str(i.get(c, '') if i.get(c) is not None else '—'))}</td>" for c in cols) + "</tr>" for i in items)

    findings_html = "".join(
        f"<div class='f'><b style='color:{sev_color.get(f['severity'], '#333')}'>[{e(f['severity'])}]</b> "
        f"<b>{e(f['code'])}</b> <span class='m'>({e(f.get('agent_id') or '')}; rules: {e(', '.join(f['rule_ids']) or '—')})</span>"
        f"<div>{e(f['summary'])}</div>"
        + (f"<div class='m'>Next step: {e(f['next_steps'][0])}</div>" if f["next_steps"] else "")
        + (f"<div class='m'>Evidence: {e('; '.join(r['title'] + ' — ' + r['section'] + ' [' + r['chunk_id'] + ']' for r in f['references']))}</div>"
           if f["references"] else f"<div class='m'>Evidence: {e(f['evidence_status'])}</div>")
        + f"<div class='m'>Source observations: {e(', '.join(f['evidence_observation_ids'][:8]) or 'none')}</div></div>"
        for f in report["findings"])
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>ASTRAHEALTH report {e(report['report_id'])}</title>
<style>body{{font:13px/1.45 system-ui,Segoe UI,sans-serif;color:#14263C;margin:32px;max-width:960px}}
h1{{font-size:22px;margin:0}}h2{{font-size:15px;border-bottom:2px solid #20B8AD;padding-bottom:4px;margin-top:28px}}
.d{{background:#FFF4E5;border:1px solid #B7791F;padding:10px;border-radius:6px;font-weight:600}}
table{{border-collapse:collapse;width:100%;font-size:11.5px}}td,th{{border:1px solid #d5dbe3;padding:4px 6px;text-align:left}}
th{{background:#14263C;color:#fff}}.m{{color:#5b6b80;font-size:11.5px}}.f{{margin:8px 0;padding:8px;border:1px solid #e3e7ee;border-radius:6px}}
.syn{{display:inline-block;background:#D8C7FF;color:#3b2a5a;padding:2px 8px;border-radius:99px;font-size:11px;font-weight:700}}</style></head><body>
<h1>ASTRAHEALTH AI — Mission Health Report</h1>
<p>{'<span class="syn">SYNTHETIC DATA</span> ' if report['is_synthetic'] else ''}Report {e(report['report_id'])} · generated {e(report['generated_at'])}</p>
<p class="d">{e(report['disclaimer'])}</p>
<h2>Header</h2><table><tr><th>Profile</th><th>Mission</th><th>Mission day</th><th>Window</th><th>Versions</th></tr>
<tr><td>{e(h['profile_alias'])} ({e(h['profile_id'])})</td><td>{e(h['mission'])} — {e(h['environment'])}</td><td>{e(str(h['mission_day']))}</td>
<td>{e(h['window_start'])} → {e(h['window_end'])}</td><td>app {e(report['versions']['app'])}; rules {e(report['versions']['ruleset'])}
({e(report['versions']['ruleset_status'])}); {e(report['versions']['anomaly_model'])}; index {e(str(report['versions']['knowledge_index']))}</td></tr></table>
<h2>Latest assessment</h2><p><b>{e(a.get('state_label', 'No analysis in window'))}</b> — {e(a.get('headline', ''))}</p>
<p class="m">Human review required: {e(str(a.get('requires_human_review', '—')))} · Coverage complete: {e(str((a.get('coverage') or {}).get('complete', '—')))}
· Unresolved REVIEW/URGENT alerts: {report['unresolved_alerts']}</p>
<h2>Findings</h2>{findings_html or '<p>No findings in window.</p>'}
<h2>Alerts</h2><table><tr><th>Severity</th><th>Title</th><th>Reason</th><th>Next step</th><th>State</th><th>Created</th></tr>
{rows(report['alerts'], ['severity', 'title', 'reason', 'next_step', 'state', 'created_at'])}</table>
<h2>Metric summary</h2><table><tr><th>Metric</th><th>Unit</th><th>n</th><th>Min</th><th>Median</th><th>Max</th></tr>
{rows(report['metric_summaries'], ['label', 'unit', 'n', 'min', 'median', 'max'])}</table>
<h2>Measurements ({len(report['measurements'])})</h2><table><tr><th>Measured (UTC)</th><th>Metric</th><th>Value</th><th>Unit</th><th>Normalized</th><th>Source</th><th>Quality</th><th>ID</th></tr>
{rows(report['measurements'], ['measured_at', 'label', 'value', 'unit', 'normalized_value', 'source', 'quality_status', 'observation_id'])}</table>
<h2>Sources</h2><ul>{''.join(f"<li>{e(s['title'])} — {e(s['publisher'])}, v{e(str(s['version']))} ({e(str(s['publication_date']))})</li>" for s in report['sources']) or '<li>No evidence cited.</li>'}</ul>
<p class="m">Print this page to PDF for a portable copy. Exported files are not encrypted by the application.</p>
</body></html>"""
