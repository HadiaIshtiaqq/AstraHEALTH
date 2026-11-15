"""Regression tests for the third review round (safety, security, Earth-Link, care plan)."""
import base64
import importlib.util
import json
import pathlib
import zlib

import pytest

from tests.conftest import ADMIN, now_iso

P1, P2, P3 = "crew-demo-01", "crew-demo-02", "crew-demo-03"


def obs(code, value, unit, **kw):
    return {"metric_code": code, "value": value, "unit": unit, "measured_at": kw.pop("measured_at", now_iso()),
            "source": "manual", **kw}


def sub(client, profile, items):
    r = client.post("/api/v1/checkins", json={"profile_id": profile, "observations": items})
    assert r.status_code == 201, r.text
    return r.json()


def test_retracting_urgent_symptom_needs_officer_and_state_stays_urgent(client):
    client.post(f"/api/v1/profiles/{P3}/reset?confirm=true", headers=ADMIN)
    r = sub(client, P3, [obs("symptom", "chest_pain", "code")])
    oid = r["checkin"]["observations"][0]["observation_id"]
    assert client.post(f"/api/v1/observations/{oid}/retract", json={"reason": "oops"}).status_code == 403
    res = client.post(f"/api/v1/observations/{oid}/retract",
                      json={"reason": "entered for the wrong crew member", "pin": "111111"}).json()
    run = client.get(f"/api/v1/analysis-runs/{res['run_id']}").json()
    # The urgent alert is still open, so the state is held at URGENT until the officer acknowledges it.
    assert run["assessment"]["monitoring_state"] == "URGENT" and run["assessment"].get("urgent_held_by_alert")


def test_one_notification_per_urgent_event(client):
    client.post(f"/api/v1/profiles/{P3}/reset?confirm=true", headers=ADMIN)
    client.post("/api/v1/demo/scenarios/urgent/run", headers=ADMIN)
    alerts = client.get(f"/api/v1/profiles/{P3}/alerts?state=open").json()["alerts"]
    assert len(alerts) == 1 and alerts[0]["severity"] == "URGENT" and "other item" in alerts[0]["reason"]


def test_pin_lockout(client):
    from app.core import security
    security._failures.clear()
    sub(client, P3, [obs("symptom", "fainting", "code")])
    aid = next(a for a in client.get(f"/api/v1/profiles/{P3}/alerts?state=open").json()["alerts"]
               if a["severity"] == "URGENT")["alert_id"]
    codes = [client.post(f"/api/v1/alerts/{aid}/acknowledge", json={"pin": f"9{i:05d}"}).status_code for i in range(6)]
    assert codes[:5] == [403] * 5 and codes[5] == 429
    assert client.post(f"/api/v1/alerts/{aid}/acknowledge", json={"pin": "111111"}).status_code == 429  # locked
    security._failures.clear()


def test_pins_hashed_and_free_text_encrypted_at_rest(client, db):
    from app.core.security import credentials_path
    creds = credentials_path().read_text(encoding="utf-8")
    data = json.loads(creds)
    assert data["version"] == 3

    def values(o):
        if isinstance(o, dict):
            for v in o.values():
                yield from values(v)
        elif isinstance(o, list):
            for v in o:
                yield from values(v)
        else:
            yield o
    assert not {"111111", "222222"} & {str(v) for v in values(data)}  # PINs only ever stored as hashes
    assert set(data["pins"]["admin_pin"]) == {"salt", "hash"}
    r = client.post("/api/v1/checkins", json={"profile_id": P1, "mode": "conversation", "raw_input_text": "private note about my mood",
                                              "observations": [obs("mood", 3, "score")]}).json()
    stored = db.one("SELECT raw_input_text FROM checkins WHERE checkin_id = ?", (r["checkin_id"],))["raw_input_text"]
    assert stored.startswith("enc:v1:") and "private" not in stored
    assert client.get(f"/api/v1/checkins/{r['checkin_id']}").json()["raw_input_text"] == "private note about my mood"


def test_double_submit_is_idempotent(client):
    payload = {"profile_id": P1, "observations": [obs("symptom", "headache", "code", measured_at=now_iso()),
                                                   obs("mood", 3, "score")]}
    a = client.post("/api/v1/checkins", json=payload).json()
    b = client.post("/api/v1/checkins", json=payload).json()
    assert b["checkin_id"] == a["checkin_id"] and b.get("duplicate") is True


def test_overview_has_baselines_for_all_metrics(client):
    ov = client.get(f"/api/v1/profiles/{P3}/overview").json()
    for m in ("exercise_duration", "fluid_intake", "heart_rate", "sleep_duration"):
        assert ov["computed_baselines"][m]["available"], m


def test_care_plan_progress_and_task_removal(client):
    client.post(f"/api/v1/profiles/{P2}/reset?confirm=true", headers=ADMIN)
    plan = client.get(f"/api/v1/profiles/{P2}/care-plan").json()
    sleep_item = next(i for i in plan["items"] if i["plan_id"] == "sleep")
    assert sleep_item["progress"]["status"] in ("not_yet", "on_track", "achieved")
    assert "usual range" in sleep_item["progress"]["detail"]
    client.post(f"/api/v1/profiles/{P2}/care-plan/sleep/adopt")
    tasks = client.get(f"/api/v1/profiles/{P2}/tasks").json()["today"]
    cp = next(t for t in tasks if t["title"].endswith("(care plan)"))
    routine = next(t for t in tasks if not t["title"].endswith("(care plan)"))
    assert client.delete(f"/api/v1/tasks/{cp['task_id']}").status_code == 200
    assert client.delete(f"/api/v1/tasks/{routine['task_id']}").status_code == 409


def test_crew_friendly_cross_domain_text(client):
    client.post(f"/api/v1/profiles/{P2}/reset?confirm=true", headers=ADMIN)
    run = client.get(f"/api/v1/profiles/{P2}/overview").json()["latest_run"]
    f = next(f for f in run["assessment"]["findings"] if f["code"] == "CROSS_DOMAIN_PATTERN")
    assert "guard" not in f["summary"] and "sleep" in f["summary"]


def test_backup_respects_disk_space(client):
    res = client.post("/api/v1/system/backup", headers=ADMIN).json()
    assert res["ok"] or res["reason"].startswith("skipped")


def test_input_sense_ranges_and_neutral_mood(client):
    def parse(text):
        r = client.post("/api/v1/input/parse", json={"profile_id": P1, "text": text}).json()
        return {o["metric_code"]: o for o in r["observations"]}, r
    hr, r = parse("my pulse is in the 80s")
    assert hr["heart_rate"]["value"] == 85 and any(c["field"] == "value" for c in r["clarifications"])
    assert parse("Feeling not too bad today")[0]["mood"]["value"] == 3


def test_llm_statements_must_be_grounded_in_findings():
    from app.safety.llm_guard import validate_explanation
    findings = [{"code": "SLEEP_SHORT_PATTERN", "severity": "MONITOR", "summary": "4 of the last 5 sleep periods were shorter than usual.",
                 "limitations": [], "next_steps": []}]
    out = validate_explanation({"statements": [{"type": "interpretation", "text": "Your immune system is probably weakened.",
                                                "finding_codes": ["SLEEP_SHORT_PATTERN"]}]}, findings, [], "MONITOR")
    assert not out["accepted"]
