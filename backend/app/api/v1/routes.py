"""Internal application API (TRD 2.5). Served on localhost only."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse, Response

from app.agents.input_sense import InputSenseAgent
from app.core import netguard
from app.core.security import (credentials_path, initial_secrets_path, key_protection, require_admin,
                               require_device_token, require_medical_officer_pin, security_events)
from app.core.config import APP_VERSION, settings
from app.db.database import dumps, get_db, iso, new_id, parse_iso, utcnow
from app.domain.metrics import METRICS, SYMPTOMS
from app.intelligence import local_llm
from app.ml.isolation_forest import MODEL_NAME, MODEL_VERSION
from app.orchestration.orchestrator import describe_agents, explanation_busy, generate_explanation_for_run, run_analysis
from app.rag.index import knowledge_index
from app.safety.rules import get_ruleset
from app.schemas.models import (
    AckIn, AnalysisRunIn, CheckinIn, ConfirmIn, CorrectIn, DeviceRecordsIn, EncryptedExportIn, ImportIn,
    ParseTextIn, ProfileIn, ProfileUpdate, ReportIn, RetractIn, TaskCompleteIn,
)
from app.seed import synthetic
from app.services import repository as repo
from app.services import reports as report_svc
from app.services import corrections, exporting, imports
from app.services import tasks as task_svc
from app.services.checkins import CheckinRejected, DuplicateSubmission, create_checkin, preview, public_preview

router = APIRouter(prefix="/api/v1")
_input_sense = InputSenseAgent()


def _profile_or_404(profile_id: str) -> dict:
    profile = repo.get_profile(get_db(), profile_id)
    if profile is None:
        raise HTTPException(404, f"Profile {profile_id} not found")
    return profile


# ---------------------------------------------------------------- reference data
@router.get("/metrics")
def metric_registry():
    return {
        "metrics": [{"code": m.code, "label": m.label, "system": m.system, "normalized_unit": m.normalized_unit,
                     "units": list(m.units), "value_type": m.value_type, "plausible_range": m.plausible_range,
                     "scale_labels": list(m.scale_labels), "description": m.description, "agents": list(m.agents)}
                    for m in METRICS.values()],
        "symptoms": [{"code": k, **v} for k, v in SYMPTOMS.items()],
    }


@router.get("/agents")
def agents():
    return {"agents": describe_agents()}


@router.get("/rules")
def rules():
    return get_ruleset().describe()


# ---------------------------------------------------------------- profiles
@router.get("/profiles")
def list_profiles():
    return {"profiles": repo.list_profiles(get_db())}


@router.post("/profiles", status_code=201)
def create_profile(body: ProfileIn):
    db = get_db()
    if db.one("SELECT 1 AS x FROM mission_contexts WHERE mission_id = ?", (body.mission_id,)) is None:
        raise HTTPException(422, "Unknown mission_id")
    profile_id = new_id("crew")
    with db.transaction() as conn:
        conn.execute("INSERT INTO crew_profiles VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (profile_id, body.display_name, body.role, body.mission_id, "{}",
                      dumps({"exercise_target_min": 120, "resistance_sessions_per_week": 6, **body.settings}),
                      body.timezone, None, 0, iso(utcnow())))  # user-created profiles hold real (non-synthetic) data
    repo.audit(db, "profile.created", profile_id, actor_role="admin")
    return repo.get_profile(db, profile_id)


def _all_baselines(profile: dict) -> dict:
    """Personal baselines for every metric (not only the ones in the last check-in)."""
    from app.agents.base import AgentContext
    from app.agents.baseline_iq import compute_baselines

    now = utcnow()
    history = repo.get_observations(get_db(), profile["profile_id"], start=now - timedelta(days=40), analysable_only=True)
    ctx = AgentContext(run_id="baseline-view", profile=profile, reference_time=now, checkin_id=None,
                       checkin_observations=(), history=tuple(history))
    codes = {m for m, d in METRICS.items() if d.value_type != "categorical"}
    baselines = compute_baselines(ctx, codes, settings.min_baseline_points)
    for b in baselines.values():
        for k in ("current", "robust_z", "pct_change"):
            b.pop(k, None)
    return baselines


@router.get("/profiles/{profile_id}")
def get_profile(profile_id: str):
    profile = _profile_or_404(profile_id)
    return {**profile, "computed_baselines": _all_baselines(profile)}


@router.patch("/profiles/{profile_id}")
def update_profile(profile_id: str, body: ProfileUpdate):
    profile = _profile_or_404(profile_id)
    db = get_db()
    new_settings = {**profile["settings"], **(body.settings or {})}
    with db.transaction() as conn:
        conn.execute("UPDATE crew_profiles SET display_name = ?, role = ?, timezone = ?, settings_json = ? WHERE profile_id = ?",
                     (body.display_name or profile["display_name"], body.role or profile["role"],
                      body.timezone or profile["timezone"], dumps(new_settings), profile_id))
    repo.audit(db, "profile.updated", profile_id, actor_role="admin", fields=sorted((body.settings or {}).keys()))
    return repo.get_profile(db, profile_id)


@router.post("/profiles/{profile_id}/reset", dependencies=[Depends(require_admin)])
def reset_profile(profile_id: str, confirm: bool = Query(False)):
    _profile_or_404(profile_id)
    if not confirm:
        raise HTTPException(400, "Reset requires confirm=true")
    synthetic.reset_profile(get_db(), profile_id)
    return {"reset": profile_id}


@router.delete("/profiles/{profile_id}", dependencies=[Depends(require_admin)])
def delete_profile(profile_id: str, confirm: bool = Query(False)):
    _profile_or_404(profile_id)
    if not confirm:
        raise HTTPException(400, "Delete requires confirm=true")
    db = get_db()
    with db.transaction() as conn:
        conn.execute("DELETE FROM crew_profiles WHERE profile_id = ?", (profile_id,))
    repo.audit(db, "profile.deleted", profile_id, actor_role="admin")
    return {"deleted": profile_id}


# ---------------------------------------------------------------- input
@router.post("/input/parse")
def parse_text(body: ParseTextIn):
    _profile_or_404(body.profile_id)
    result = _input_sense.parse(body.text, utcnow())
    repo.audit(get_db(), "input.parsed", body.profile_id, actor_role="crew", candidates=len(result["observations"]))
    return result


@router.post("/checkins/validate")
def validate_checkin(body: CheckinIn):
    _profile_or_404(body.profile_id)
    return public_preview(preview(get_db(), body))


@router.post("/checkins", status_code=201)
def submit_checkin(body: CheckinIn):
    db = get_db()
    _profile_or_404(body.profile_id)
    try:
        checkin_id = create_checkin(db, body, is_synthetic=True)
    except CheckinRejected as exc:
        raise HTTPException(422, {"message": "Check-in rejected: fix the listed fields. Nothing was saved.", "errors": exc.errors})
    except DuplicateSubmission as dup:
        # Idempotent replay (double click / resend): return the original check-in, do not store it twice.
        prior = db.one("SELECT run_id FROM analysis_runs WHERE checkin_id = ? ORDER BY started_at DESC, rowid DESC LIMIT 1",
                       (dup.checkin_id,))
        return {"checkin_id": dup.checkin_id, "run_id": prior["run_id"] if prior else None,
                "checkin": repo.get_checkin(db, dup.checkin_id), "duplicate": True}
    run_id = None
    if body.run_analysis:
        run_id = run_analysis(db, body.profile_id, checkin_id)
    return {"checkin_id": checkin_id, "run_id": run_id, "checkin": repo.get_checkin(db, checkin_id)}


@router.get("/checkins/{checkin_id}")
def get_checkin(checkin_id: str):
    checkin = repo.get_checkin(get_db(), checkin_id)
    if checkin is None:
        raise HTTPException(404, "Check-in not found")
    return checkin


@router.get("/profiles/{profile_id}/checkins")
def list_checkins(profile_id: str, limit: int = 20):
    _profile_or_404(profile_id)
    rows = get_db().query("SELECT checkin_id, submitted_at, mode, is_synthetic FROM checkins WHERE profile_id = ? "
                          "ORDER BY submitted_at DESC LIMIT ?", (profile_id, limit))
    return {"checkins": rows}


# ---------------------------------------------------------------- metrics
@router.get("/metrics/{profile_id}")
def metric_series(profile_id: str, metric: list[str] = Query(default=[]), days: int = 30,
                  start: str | None = None, end: str | None = None):
    _profile_or_404(profile_id)
    end_dt = parse_iso(end) if end else utcnow() + timedelta(minutes=5)
    start_dt = parse_iso(start) if start else end_dt - timedelta(days=days)
    obs = repo.get_observations(get_db(), profile_id, metric_codes=metric or None, start=start_dt, end=end_dt)
    series: dict[str, list] = {}
    for o in obs:
        series.setdefault(o["metric_code"], []).append({
            "observation_id": o["observation_id"], "measured_at": o["measured_at"], "value": o["value"],
            "value_text": o["value_text"], "unit": o["unit"], "normalized_value": o["normalized_value"],
            "normalized_unit": o["normalized_unit"], "source": o["source"], "context": o["context"],
            "quality_status": o["quality_status"], "quality_flags": o["quality_flags"], "is_synthetic": o["is_synthetic"],
        })
    return {"profile_id": profile_id, "start": iso(start_dt), "end": iso(end_dt), "series": series}


@router.get("/profiles/{profile_id}/overview")
def overview(profile_id: str):
    profile = _profile_or_404(profile_id)
    db = get_db()
    now = utcnow()
    latest: dict[str, dict] = {}
    for o in repo.get_observations(db, profile_id, start=now - timedelta(days=14)):
        if o["quality_status"] == "valid" or o["metric_code"] not in latest:
            latest[o["metric_code"]] = o
    run = repo.latest_run(db, profile_id)
    today = task_svc.local_today(db, profile_id)
    from app.ml.stats import local_date
    recent = db.query("SELECT submitted_at FROM checkins WHERE profile_id = ? AND mode IN ('manual', 'conversation') "
                      "AND submitted_at >= ?", (profile_id, iso(now - timedelta(days=2))))
    checked_in_today = any(local_date(r["submitted_at"], profile["timezone"]) == today for r in recent) or None
    tasks = task_svc.list_tasks(db, profile_id, days=1)
    last_urgent_ack = db.one("SELECT alert_id, acknowledged_at, acknowledged_note FROM alerts WHERE profile_id = ? "
                             "AND severity = 'URGENT' AND state = 'acknowledged' ORDER BY acknowledged_at DESC LIMIT 1",
                             (profile_id,))
    return {
        "computed_baselines": _all_baselines(profile),
        "urgent_acknowledged": last_urgent_ack,
        "profile": profile,
        "latest_values": latest,
        "latest_run": run,
        "open_alerts": repo.get_alerts(db, profile_id, state="open"),
        "checkin_due": checked_in_today is None,
        "tasks_today": tasks["today"],
        "checkin_streak": tasks["checkin_streak"],
    }


# ---------------------------------------------------------------- analysis
@router.post("/analysis-runs", status_code=201)
def create_run(body: AnalysisRunIn, x_admin_pin: str | None = Header(default=None)):
    _profile_or_404(body.profile_id)
    if body.simulate_failure:  # fault injection is a demo/reviewer control
        require_admin(x_admin_pin)
    try:
        run_id = run_analysis(get_db(), body.profile_id, body.checkin_id, body.simulate_failure,
                              body.requested_agents, body.generate_explanation)
    except (LookupError, ValueError) as exc:
        raise HTTPException(404, str(exc))
    return repo.get_run(get_db(), run_id)


@router.get("/analysis-runs/{run_id}")
def get_run(run_id: str):
    run = repo.get_run(get_db(), run_id)
    if run is None:
        raise HTTPException(404, "Analysis run not found")
    return run


@router.post("/analysis-runs/{run_id}/explain")
def regenerate_explanation(run_id: str):
    db = get_db()
    run = repo.get_run(db, run_id)
    if run is None:
        raise HTTPException(404, "Analysis run not found")
    if run["explanation_status"] in ("pending", "running") or explanation_busy():
        raise HTTPException(409, "The local model is already writing an explanation; try again when it finishes.")
    import threading
    with db.transaction() as conn:
        conn.execute("UPDATE analysis_runs SET explanation_status = 'pending' WHERE run_id = ?", (run_id,))
    threading.Thread(target=generate_explanation_for_run, args=(db, run_id), daemon=True).start()
    return {"run_id": run_id, "explanation_status": "pending"}


@router.get("/profiles/{profile_id}/analysis-runs")
def list_runs(profile_id: str, limit: int = 15):
    _profile_or_404(profile_id)
    rows = get_db().query("SELECT run_id, checkin_id, status, overall_status, coverage, started_at, completed_at, "
                          "ruleset_version, explanation_status FROM analysis_runs WHERE profile_id = ? "
                          "ORDER BY started_at DESC, rowid DESC LIMIT ?", (profile_id, limit))
    return {"runs": rows}


# ---------------------------------------------------------------- alerts
@router.get("/profiles/{profile_id}/alerts")
def list_alerts(profile_id: str, state: str | None = None):
    _profile_or_404(profile_id)
    return {"alerts": repo.get_alerts(get_db(), profile_id, state=state)}


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: str, body: AckIn):
    db = get_db()
    alert = db.one("SELECT * FROM alerts WHERE alert_id = ?", (alert_id,))
    if alert is None:
        raise HTTPException(404, "Alert not found")
    if alert["state"] != "open":
        raise HTTPException(409, f"Alert is already {alert['state']}")
    role = body.actor_role
    if alert["severity"] == "URGENT":
        # Only the medical officer can clear an urgent alert; the crew member cannot dismiss it.
        require_medical_officer_pin(body.pin)
        role = "medical_officer"
    with db.transaction() as conn:
        conn.execute("UPDATE alerts SET state = 'acknowledged', acknowledged_at = ?, acknowledged_by = ?, "
                     "acknowledged_note = ? WHERE alert_id = ?", (iso(utcnow()), role, body.note, alert_id))
    repo.audit(db, "alert.acknowledged", alert_id, actor_role=role, severity=alert["severity"])
    return db.one("SELECT * FROM alerts WHERE alert_id = ?", (alert_id,))


# ---------------------------------------------------------------- tasks
@router.get("/profiles/{profile_id}/tasks")
def list_tasks(profile_id: str, days: int = 7):
    _profile_or_404(profile_id)
    return task_svc.list_tasks(get_db(), profile_id, days)


@router.post("/tasks/{task_id}/complete")
def complete_task(task_id: str, body: TaskCompleteIn):
    try:
        return task_svc.complete_task(get_db(), task_id, body.note)
    except LookupError:
        raise HTTPException(404, "Task not found")


@router.delete("/tasks/{task_id}")
def remove_task(task_id: str):
    try:
        return task_svc.remove_task(get_db(), task_id)
    except LookupError:
        raise HTTPException(404, "Task not found")
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@router.post("/tasks/{task_id}/reopen")
def reopen_task(task_id: str):
    return task_svc.undo_task(get_db(), task_id)


# ---------------------------------------------------------------- reports
@router.post("/reports", status_code=201)
def create_report(body: ReportIn):
    _profile_or_404(body.profile_id)
    try:
        return report_svc.build_report(get_db(), body.profile_id, body.start, body.end)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get("/reports/{report_id}")
def get_report(report_id: str):
    report = report_svc.get_report(get_db(), report_id)
    if report is None:
        raise HTTPException(404, "Report not found")
    return report


@router.get("/reports/{report_id}/export.csv", response_class=PlainTextResponse)
def export_csv(report_id: str):
    report = get_report(report_id)
    repo.audit(get_db(), "report.exported", report_id, actor_role="crew", format="csv")
    return PlainTextResponse(report_svc.to_csv(report), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="astrahealth-{report_id}.csv"'})


@router.get("/reports/{report_id}/export.html", response_class=HTMLResponse)
def export_html(report_id: str):
    report = get_report(report_id)
    repo.audit(get_db(), "report.exported", report_id, actor_role="crew", format="html")
    return HTMLResponse(report_svc.to_html(report))


# ---------------------------------------------------------------- knowledge
@router.get("/knowledge/search")
def knowledge_search(q: str = Query(..., min_length=2, max_length=300), k: int = 3):
    if not knowledge_index.ready:
        return {"available": False, "results": [], "reason": knowledge_index.error}
    return {"available": True, "results": knowledge_index.search(q, k=min(k, 8))}


@router.get("/knowledge/documents")
def knowledge_documents():
    return {"documents": get_db().query("SELECT * FROM knowledge_documents ORDER BY document_id"),
            "index": knowledge_index.status()}


@router.post("/knowledge/rebuild", dependencies=[Depends(require_admin)])
def knowledge_rebuild():
    status = knowledge_index.build(get_db())
    repo.audit(get_db(), "knowledge.rebuilt", None, actor_role="admin", chunks=status["chunks"])
    return status


# ---------------------------------------------------------------- demo
@router.get("/demo/scenarios")
def demo_scenarios():
    return {"scenarios": [{"id": k, **v} for k, v in synthetic.SCENARIOS.items()]}


@router.post("/demo/scenarios/{scenario}/run", status_code=201, dependencies=[Depends(require_admin)])
def run_scenario(scenario: str):
    db = get_db()
    if scenario not in synthetic.SCENARIOS:
        raise HTTPException(404, "Unknown scenario")
    if scenario == "agent_failure":
        run_id = run_analysis(db, "crew-demo-01", None, simulate_failure=["sleep_sense"])
        return {"run_id": run_id, "profile_id": "crew-demo-01", "checkin_id": None}
    payload = synthetic.scenario_checkin(scenario)
    try:
        checkin_id = create_checkin(db, payload, is_synthetic=True)
    except DuplicateSubmission as dup:  # same scripted check-in resent: reuse the original
        prior = db.one("SELECT run_id FROM analysis_runs WHERE checkin_id = ? ORDER BY started_at DESC, rowid DESC LIMIT 1",
                       (dup.checkin_id,))
        return {"run_id": prior["run_id"], "profile_id": payload.profile_id, "checkin_id": dup.checkin_id, "duplicate": True}
    run_id = run_analysis(db, payload.profile_id, checkin_id)
    return {"run_id": run_id, "profile_id": payload.profile_id, "checkin_id": checkin_id}


@router.post("/demo/reseed", dependencies=[Depends(require_admin)])
def reseed(confirm: bool = Query(False)):
    if not confirm:
        raise HTTPException(400, "Reseed requires confirm=true")
    db = get_db()
    with db.transaction() as conn:
        conn.execute("DELETE FROM crew_profiles")
    synthetic.seed_all(db, force=True)
    return {"reseeded": True}


# ---------------------------------------------------------------- care plan
@router.get("/profiles/{profile_id}/care-plan")
def care_plan(profile_id: str):
    _profile_or_404(profile_id)
    run = repo.latest_run(get_db(), profile_id)
    if run is None:
        return {"items": [], "message": "No analysis yet.", "state": "INCOMPLETE"}
    plan = {**run["assessment"].get("care_plan", {"items": []}), "run_id": run["run_id"]}
    from app.safety.care_plan import progress_for
    profile = _profile_or_404(profile_id)
    history = repo.get_observations(get_db(), profile_id, start=utcnow() - timedelta(days=10), analysable_only=True)
    baselines = _all_baselines(profile)
    for item in plan.get("items", []):
        item["progress"] = progress_for(item, history, baselines, profile.get("timezone") or "UTC")
    return plan


@router.post("/profiles/{profile_id}/care-plan/{plan_id}/adopt", status_code=201)
def adopt_care_plan(profile_id: str, plan_id: str):
    plan = care_plan(profile_id)
    item = next((i for i in plan.get("items", []) if i["plan_id"] == plan_id), None)
    if item is None:
        raise HTTPException(404, "This recommendation is not part of the current care plan")
    created = task_svc.add_plan_tasks(get_db(), profile_id, item)
    return {"created": created, "plan_id": plan_id}


# ---------------------------------------------------------------- corrections
def _rerun(db, observation: dict, rerun: bool) -> str | None:
    if not rerun or not observation.get("checkin_id"):
        return None
    return run_analysis(db, observation["profile_id"], observation["checkin_id"])


@router.post("/observations/{observation_id}/confirm")
def confirm_observation(observation_id: str, body: ConfirmIn):
    db = get_db()
    try:
        obs = corrections.confirm(db, observation_id, body.note, body.pin, body.actor_role)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return {"observation": obs, "run_id": _rerun(db, obs, body.rerun)}


@router.post("/observations/{observation_id}/correct")
def correct_observation(observation_id: str, body: CorrectIn):
    db = get_db()
    try:
        obs = corrections.correct(db, observation_id, body.value, body.unit, body.reason, pin=body.pin)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return {"observation": obs, "run_id": _rerun(db, obs, body.rerun)}


@router.post("/observations/{observation_id}/retract")
def retract_observation(observation_id: str, body: RetractIn):
    db = get_db()
    try:
        obs = corrections.retract(db, observation_id, body.reason, pin=body.pin)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return {"observation": obs, "run_id": _rerun(db, obs, body.rerun)}


# ---------------------------------------------------------------- imports & devices
@router.post("/imports", dependencies=[Depends(require_admin)])
def import_records(body: ImportIn):
    db = get_db()
    _profile_or_404(body.profile_id)
    try:
        rows = imports.parse_rows(body.content, body.format)
        if any(str(r.get("metric_code", "")).strip() == "symptom" for r in rows if isinstance(r, dict)):
            raise ValueError("Imports cannot contain symptom reports; symptoms come from the crew member's own check-in.")
        result = imports.import_records(db, body.profile_id, rows, "import", f"{body.format}_import", body.dry_run)
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, str(exc))
    if result["checkin_id"]:
        result["run_id"] = run_analysis(db, body.profile_id, result["checkin_id"])
    return result


@router.post("/devices/{device_id}/records", dependencies=[Depends(require_device_token)])
def device_records(device_id: str, body: DeviceRecordsIn):
    """Device adapter (needs X-Device-Token). Devices may only send measurements, never symptom reports."""
    db = get_db()
    _profile_or_404(body.profile_id)
    if any(str(r.get("metric_code")) == "symptom" for r in body.records):
        raise HTTPException(422, "Devices cannot report symptoms; symptoms come from the crew member.")
    try:
        result = imports.import_records(db, body.profile_id, body.records, "device", f"device:{device_id[:40]}", False)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    if result["checkin_id"]:
        result["run_id"] = run_analysis(db, body.profile_id, result["checkin_id"])
    return result


# ---------------------------------------------------------------- report exports
@router.get("/reports/{report_id}/export.pdf")
def export_pdf(report_id: str):
    report = get_report(report_id)
    repo.audit(get_db(), "report.exported", report_id, actor_role="crew", format="pdf")
    return Response(exporting.render_pdf(report), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="astrahealth-{report_id}.pdf"'})


@router.post("/reports/{report_id}/export.enc")
def export_encrypted(report_id: str, body: EncryptedExportIn):
    report = get_report(report_id)
    data = {"pdf": lambda: exporting.render_pdf(report), "csv": lambda: report_svc.to_csv(report).encode(),
            "html": lambda: report_svc.to_html(report).encode()}[body.format]()
    try:
        blob = exporting.encrypt(data, body.passphrase)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    repo.audit(get_db(), "report.exported", report_id, actor_role="crew", format=f"{body.format}+encrypted")
    return Response(blob, media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="astrahealth-{report_id}.{body.format}.astra.enc"'})


# ---------------------------------------------------------------- system
@router.get("/system/health")
def system_health():
    db = get_db()
    db_ok = db.ping()
    size = settings.database_path.stat().st_size if settings.database_path.exists() else 0
    llm = local_llm.health()
    ruleset = get_ruleset()
    guard = netguard.status()
    return {
        "app_version": APP_VERSION,
        "mode": settings.app_mode,
        "offline": {"allow_external_network": settings.allow_external_network, "guard_installed": guard["installed"],
                    "blocked_attempts": guard["blocked_attempts"], "last_blocked": guard["last_blocked"]},
        "database": {"ok": db_ok, "path": str(settings.database_path.name), "size_kb": round(size / 1024, 1),
                     "engine": "SQLite (stdlib sqlite3)"},
        "llm": llm,
        "knowledge_index": knowledge_index.status(),
        "ruleset": {"version": ruleset.version, "status": ruleset.status, "checksum": ruleset.checksum, "rules": len(ruleset.rules)},
        "anomaly_model": {"name": MODEL_NAME, "version": MODEL_VERSION},
        "synthetic_data": settings.enable_synthetic_data,
        "access_control": {"credentials_file": str(credentials_path()),
                           "initial_secrets_file_present": initial_secrets_path().exists(),
                           "key_protection": key_protection(),
                           "note": "Medical officer PIN: URGENT acknowledgement, confirming implausible values. "
                                   "Admin PIN: reset, reseed, delete, knowledge rebuild."},
        "llm_busy": explanation_busy(),
        "audit_chain": repo.verify_audit_chain(db),
        "security_events": security_events(),
        "server_time": iso(utcnow()),
    }


@router.post("/system/initial-secrets/delete", dependencies=[Depends(require_admin)])
def delete_initial_secrets():
    """The operator confirms the PINs are noted; the plain-text file is then removed (admin PIN proves it is known)."""
    path = initial_secrets_path()
    existed = path.exists()
    if existed:
        path.unlink()
        repo.audit(get_db(), "secrets.initial_file_deleted", None, actor_role="admin")
    return {"deleted": existed, "initial_secrets_file_present": path.exists()}


@router.post("/system/backup", dependencies=[Depends(require_admin)])
def system_backup():
    from app.services.backup import list_backups, make_backup
    return {**make_backup("manual"), "backups": list_backups()}


@router.get("/system/audit", dependencies=[Depends(require_admin)])
def audit_log(limit: int = 50):
    db = get_db()
    return {"events": db.query("SELECT event_id, actor_role, action, object_id, timestamp, metadata FROM audit_events "
                               "ORDER BY rowid DESC LIMIT ?", (min(limit, 500),)),
            "chain": repo.verify_audit_chain(db)}
