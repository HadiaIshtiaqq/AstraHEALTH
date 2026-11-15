"""Functional test cases TC-001 … TC-016 (test plan 5.3)."""
from datetime import timedelta

from app.db.database import iso, utcnow
from tests.conftest import ADMIN, now_iso

P1 = "crew-demo-01"


def obs(code, value, unit, **kw):
    return {"metric_code": code, "value": value, "unit": unit, "measured_at": kw.pop("measured_at", now_iso()),
            "source": "manual", **kw}


def test_tc001_valid_checkin_saved_with_ids_and_normalized_units(client):
    r = client.post("/api/v1/checkins", json={"profile_id": P1, "run_analysis": False, "observations": [
        obs("heart_rate", 63, "bpm", context="resting"), obs("body_temperature", 98.4, "°F"),
        obs("fluid_intake", 1.2, "L")]})
    assert r.status_code == 201, r.text
    saved = r.json()["checkin"]["observations"]
    assert len({o["observation_id"] for o in saved}) == 3
    temp = next(o for o in saved if o["metric_code"] == "body_temperature")
    assert temp["value"] == 98.4 and temp["unit"] == "°F"  # raw preserved
    assert abs(temp["normalized_value"] - 36.89) < 0.01 and temp["normalized_unit"] == "°C"
    fluid = next(o for o in saved if o["metric_code"] == "fluid_intake")
    assert fluid["normalized_value"] == 1200
    assert all(o["measured_at"].endswith("Z") for o in saved)


def test_tc002_missing_unit_rejected_nothing_saved(client, db):
    before = db.one("SELECT COUNT(*) n FROM observations")["n"]
    r = client.post("/api/v1/checkins", json={"profile_id": P1, "observations": [
        {"metric_code": "heart_rate", "value": 70, "measured_at": now_iso(), "source": "manual"}]})
    assert r.status_code == 422
    assert "unit is required" in str(r.json())
    assert db.one("SELECT COUNT(*) n FROM observations")["n"] == before


def test_tc002b_unknown_unit_not_converted(client):
    r = client.post("/api/v1/checkins/validate", json={"profile_id": P1, "observations": [obs("heart_rate", 70, "Hz")]})
    item = r.json()["observations"][0]
    assert not r.json()["ok"] and item["normalized_value"] is None
    assert "unknown unit" in item["errors"][0]


def test_tc003_non_numeric_value_rejected_without_crash(client):
    r = client.post("/api/v1/checkins", json={"profile_id": P1, "observations": [obs("heart_rate", "seventy", "bpm")]})
    assert r.status_code == 422 and "not a number" in str(r.json())


def test_tc004_stale_measurement_flagged_and_excluded(client):
    old = iso(utcnow() - timedelta(days=3))
    r = client.post("/api/v1/checkins", json={"profile_id": P1, "run_analysis": False,
                                               "observations": [obs("sleep_duration", 6.5, "h", measured_at=old)]})
    assert r.json()["checkin"]["observations"][0]["quality_status"] == "stale"


def test_implausible_value_kept_and_flagged_not_discarded(client):
    r = client.post("/api/v1/checkins", json={"profile_id": P1, "observations": [obs("heart_rate", 310, "bpm", context="resting")]})
    assert r.status_code == 201
    o = r.json()["checkin"]["observations"][0]
    assert o["quality_status"] == "implausible" and o["value"] == 310
    run = client.get(f"/api/v1/analysis-runs/{r.json()['run_id']}").json()
    assert any(f["code"] == "DATA_QUALITY_FLAG" for f in run["assessment"]["findings"])


def test_blood_pressure_requires_both_values(client):
    r = client.post("/api/v1/checkins", json={"profile_id": P1, "observations": [obs("bp_systolic", 120, "mmHg")]})
    assert r.status_code == 422 and "both systolic and diastolic" in str(r.json())


def test_tc005_no_baseline_not_shown_as_normal(client):
    p = client.post("/api/v1/profiles", json={"display_name": "New crew (synthetic)"}).json()
    r = client.post("/api/v1/checkins", json={"profile_id": p["profile_id"], "observations": [
        obs("heart_rate", 66, "bpm", context="resting"), obs("sleep_duration", 7, "h")]})
    run = client.get(f"/api/v1/analysis-runs/{r.json()['run_id']}").json()
    assert run["assessment"]["monitoring_state"] == "INCOMPLETE"
    assert any(f["code"] == "BASELINE_UNAVAILABLE" for f in run["assessment"]["findings"])


def test_tc006_cardio_finding_references_source_observations(client):
    r = client.post("/api/v1/demo/scenarios/gradual/run", headers=ADMIN).json()
    run = client.get(f"/api/v1/analysis-runs/{r['run_id']}").json()
    cardio = next(a for a in run["agent_results"] if a["agent_id"] == "cardio_guard")
    hr = next(f for f in cardio["findings"] if f["code"] == "HR_BASELINE_DEVIATION")
    saved_ids = {o["observation_id"] for o in client.get(f"/api/v1/checkins/{r['checkin_id']}").json()["observations"]}
    assert hr["evidence_observation_ids"] and set(hr["evidence_observation_ids"]) <= saved_ids
    assert hr["data"]["sustained"] is True


def test_tc007_stable_sequence_no_unsupported_alarm(client):
    r = client.post("/api/v1/demo/scenarios/healthy/run", headers=ADMIN).json()
    run = client.get(f"/api/v1/analysis-runs/{r['run_id']}").json()
    anomaly = next(a for a in run["agent_results"] if a["agent_id"] == "anomaly_detect")
    assert anomaly["status"] == "completed"
    assert not any(f["code"] == "MULTIVARIATE_ANOMALY" for f in anomaly["findings"])
    assert anomaly["output"]["model"]["model"].startswith("IsolationForest")
    assert run["assessment"]["monitoring_state"] == "WITHIN_CRITERIA"


def test_tc008_injected_deviation_flagged_with_limits(client):
    client.post("/api/v1/profiles/crew-demo-02/reset?confirm=true", headers=ADMIN)  # isolate from earlier tests
    r = client.post("/api/v1/demo/scenarios/gradual/run", headers=ADMIN).json()
    run = client.get(f"/api/v1/analysis-runs/{r['run_id']}").json()
    f = next(f for f in run["assessment"]["findings"] if f["code"] == "MULTIVARIATE_ANOMALY")
    assert f["data"]["contributors"] and f["limitations"] and f["data"]["input_window"]["training_days"] >= 14


def test_tc009_agent_exception_others_continue(client):
    r = client.post("/api/v1/demo/scenarios/agent_failure/run", headers=ADMIN).json()
    run = client.get(f"/api/v1/analysis-runs/{r['run_id']}").json()
    statuses = {a["agent_id"]: a["status"] for a in run["agent_results"]}
    assert statuses["sleep_sense"] == "failed"
    assert statuses["cardio_guard"] in ("completed", "review")
    assert run["assessment"]["coverage"]["complete"] is False
    assert run["assessment"]["monitoring_state"] != "WITHIN_CRITERIA"


def test_tc010_llm_stopped_rule_path_works(client):
    r = client.post("/api/v1/demo/scenarios/urgent/run", headers=ADMIN).json()
    run = client.get(f"/api/v1/analysis-runs/{r['run_id']}").json()
    assert run["assessment"]["monitoring_state"] == "URGENT"
    assert run["explanation_status"] == "disabled" and run["explanation"]["statements"]


def test_tc012_conflict_escalated_not_averaged():
    from app.safety.gate import detect_conflicts
    from app.schemas.models import AgentResult, MetricAssessment

    a = AgentResult(run_id="r", agent_id="nutri_track", agent_name="NutriTrack", agent_version="1", status="completed",
                    assessments=[MetricAssessment(metric_code="fluid_intake", assessment="stable")])
    b = AgentResult(run_id="r", agent_id="anomaly_detect", agent_name="AnomalyDetect", agent_version="1", status="completed",
                    assessments=[MetricAssessment(metric_code="fluid_intake", assessment="changed")])
    conflicts = detect_conflicts([a, b])
    assert len(conflicts) == 1
    from app.safety.rules import get_ruleset
    assert get_ruleset().apply_to_finding(conflicts[0]).severity.value == "REVIEW"


def test_tc013_export_contains_units_timestamps_versions_disclaimer(client):
    rep = client.post("/api/v1/reports", json={"profile_id": P1}).json()
    csv = client.get(f"/api/v1/reports/{rep['report_id']}/export.csv").text
    html = client.get(f"/api/v1/reports/{rep['report_id']}/export.html").text
    for text in (csv, html):
        assert "NOT A MEDICAL DEVICE" in text and "demo-1.0.0" in text
    assert "normalized_unit" in csv and "measured_at" in csv and "SYNTHETIC" in html


def test_tc014_offline_guard_blocks_external_network(client):
    import socket

    import pytest

    from app.core import netguard

    assert netguard.status()["installed"]
    with pytest.raises(OSError):
        socket.create_connection(("example.com", 80), timeout=1)
    assert client.get("/api/v1/system/health").json()["offline"]["blocked_attempts"] >= 1


def test_tc015_records_persist_across_restart(client, tmp_db_path):
    from app.db.database import Database

    r = client.post("/api/v1/checkins", json={"profile_id": P1, "run_analysis": False, "observations": [obs("mood", 4, "score")]})
    cid = r.json()["checkin_id"]
    fresh = Database(tmp_db_path)  # new connection, as after a restart
    assert fresh.one("SELECT checkin_id FROM checkins WHERE checkin_id = ?", (cid,))


def test_tc016_reset_requires_confirmation(client):
    assert client.post("/api/v1/profiles/crew-demo-03/reset", headers=ADMIN).status_code == 400
    assert client.post("/api/v1/profiles/crew-demo-03/reset?confirm=true", headers=ADMIN).status_code == 200


def test_tasks_completion_is_explicit_and_logged(client, db):
    # Only the check-in task can be completed by an action (submitting a check-in); nothing else is inferred.
    tasks = [t for t in client.get(f"/api/v1/profiles/{P1}/tasks").json()["today"] if t["category"] != "checkin"]
    assert tasks and all(t["completed_at"] is None for t in tasks)
    done = client.post(f"/api/v1/tasks/{tasks[0]['task_id']}/complete", json={}).json()
    assert done["completed_at"]
    assert db.one("SELECT 1 x FROM audit_events WHERE action = 'task.completed' AND object_id = ?", (tasks[0]["task_id"],))


def test_input_sense_extracts_and_requires_confirmation(client):
    r = client.post("/api/v1/input/parse", json={"profile_id": P1, "text":
                    "My heart rate is 105 BPM, I slept for 4 hours, and I have been feeling unusually tired. No chest pain."}).json()
    codes = {o["metric_code"]: o for o in r["observations"]}
    assert codes["heart_rate"]["value"] == 105 and codes["sleep_duration"]["value"] == 4
    assert codes["fatigue"]["value"] == 4 and r["requires_confirmation"]
    assert "chest_pain" in r["negated_symptoms"]
    assert not any(o.get("value") == "chest_pain" for o in r["observations"])
    assert all(o["confirmed"] is False for o in r["observations"])
