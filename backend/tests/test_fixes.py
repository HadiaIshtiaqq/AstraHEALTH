"""Regression tests for the flaws found in review, and for Earth-Link."""
from datetime import timedelta

import pytest

from app.db.database import iso, utcnow
from tests.conftest import ADMIN, now_iso

P1, P3 = "crew-demo-01", "crew-demo-03"


def obs(code, value, unit, **kw):
    return {"metric_code": code, "value": value, "unit": unit, "measured_at": kw.pop("measured_at", now_iso()),
            "source": "manual", **kw}


def sub(client, profile, items):
    r = client.post("/api/v1/checkins", json={"profile_id": profile, "observations": items})
    assert r.status_code == 201, r.text
    return r.json()


def test_flaw1_repeated_urgent_symptom_always_escalates(client):
    t = now_iso()
    first = sub(client, P3, [obs("symptom", "chest_pain", "code", measured_at=t)])
    second = sub(client, P3, [obs("symptom", "chest_pain", "code", measured_at=t)])  # same minute, same value
    for r in (first, second):
        run = client.get(f"/api/v1/analysis-runs/{r['run_id']}").json()
        assert run["assessment"]["monitoring_state"] == "URGENT"
        assert all(o["quality_status"] == "valid" for o in r["checkin"]["observations"])


def test_flaw2_crew_cannot_dismiss_urgent_alert(client):
    r = sub(client, P3, [obs("symptom", "fainting", "code")])
    alert = next(a for a in client.get(f"/api/v1/analysis-runs/{r['run_id']}").json()["alerts"] if a["severity"] == "URGENT")
    assert client.post(f"/api/v1/alerts/{alert['alert_id']}/acknowledge", json={"actor_role": "crew"}).status_code == 403
    assert client.post(f"/api/v1/alerts/{alert['alert_id']}/acknowledge", json={"pin": "000000"}).status_code == 403
    ok = client.post(f"/api/v1/alerts/{alert['alert_id']}/acknowledge", json={"pin": "111111", "note": "assessed"})
    assert ok.status_code == 200 and ok.json()["acknowledged_by"] == "medical_officer"


def test_flaw3_input_sense_parsing(client):
    def parse(text):
        r = client.post("/api/v1/input/parse", json={"profile_id": P1, "text": text}).json()
        return {o["metric_code"]: o for o in r["observations"]}
    assert "heart_rate" not in parse("I slept 4 hrs and drank 2 L of water")
    assert "mood" not in parse("Feeling fine, but I have chest pain")
    assert "mood" not in parse("Good sleep, feeling very stressed")
    assert parse("Did 30 min on the treadmill and 45 min resistance")["exercise_duration"]["value"] == 75
    assert parse("Pulse 72 after my workout")["heart_rate"]["context"] == "post_exercise"


def test_flaw4_guard_blocks_implied_diagnosis():
    from app.safety.llm_guard import validate_explanation
    findings = [{"code": "URGENT_SYMPTOM_REPORTED", "severity": "URGENT", "summary": "Urgent symptom reported: chest pain."}]
    for text in ["These symptoms suggest a serious condition.", "You might have a heart problem.",
                 "This is caused by radiation exposure."]:
        out = validate_explanation({"statements": [{"type": "interpretation", "text": text,
                                                    "finding_codes": ["URGENT_SYMPTOM_REPORTED"]}]}, findings, [], "URGENT")
        assert not out["accepted"], text
    unlinked = validate_explanation({"statements": [{"type": "interpretation", "text": "Rest well."}]}, findings, [], "URGENT")
    assert not unlinked["accepted"]


def test_flaw5_implausible_value_can_be_confirmed_by_medical_officer(client):
    r = sub(client, P1, [obs("heart_rate", 255, "bpm", context="resting")])
    o = r["checkin"]["observations"][0]
    assert o["quality_status"] == "implausible"
    url = f"/api/v1/observations/{o['observation_id']}/confirm"
    assert client.post(url, json={"note": "re-measured"}).status_code == 403
    res = client.post(url, json={"pin": "111111", "note": "re-measured twice"}).json()
    assert res["observation"]["quality_status"] == "valid" and res["run_id"]
    assert res["observation"]["raw"]["value"] == 255  # raw value unchanged


def test_flaw6_corrections_never_double_count(client):
    first = sub(client, P1, [obs("sleep_duration", 7, "h")])
    sid = first["checkin"]["observations"][0]["observation_id"]
    res = client.post(f"/api/v1/observations/{sid}/correct", json={"value": 7.5, "unit": "h", "reason": "typo"}).json()
    run = client.get(f"/api/v1/analysis-runs/{res['run_id']}").json()
    b = next(a for a in run["agent_results"] if a["agent_id"] == "baseline_iq")["output"]["baselines"]["sleep_duration"]
    assert b["current"] == 7.5
    old = client.get(f"/api/v1/checkins/{first['checkin_id']}").json()["observations"]
    assert any(o["observation_id"] == sid and o["quality_status"] == "superseded" for o in old)
    # Re-entering sleep in a new check-in replaces (latest report), never sums
    again = sub(client, P1, [obs("sleep_duration", 6.5, "h")])
    run2 = client.get(f"/api/v1/analysis-runs/{again['run_id']}").json()
    b2 = next(a for a in run2["agent_results"] if a["agent_id"] == "baseline_iq")["output"]["baselines"]["sleep_duration"]
    assert b2["current"] == 6.5


def test_flaw7_demo_clock_shift(client, db):
    from app.seed.synthetic import shift_demo_clock
    with db.transaction() as conn:  # simulate a database seeded 3 days ago
        conn.execute("UPDATE checkins SET submitted_at = strftime('%Y-%m-%dT%H:%M:%SZ', replace(submitted_at,'Z',''), '-3 days')")
    before = db.one("SELECT MAX(submitted_at) m FROM checkins WHERE mode='simulated'")["m"]
    assert shift_demo_clock(db) == 3
    after = db.one("SELECT MAX(submitted_at) m FROM checkins WHERE mode='simulated'")["m"]
    assert after > before and shift_demo_clock(db) == 0


def test_flaw8_local_day_boundaries():
    from app.ml.stats import daily_series
    o = [{"metric_code": "exercise_duration", "normalized_value": 60, "quality_status": "valid",
          "measured_at": "2026-11-14T22:30:00Z"}]
    assert list(daily_series(o, "exercise_duration", "UTC"))[0].isoformat() == "2026-11-14"
    assert list(daily_series(o, "exercise_duration", "Asia/Karachi"))[0].isoformat() == "2026-11-15"


def test_flaw10_alerts_are_consolidated_and_deduplicated(client, db):
    client.post("/api/v1/profiles/crew-demo-02/reset?confirm=true", headers=ADMIN)
    for _ in range(2):
        client.post("/api/v1/analysis-runs", json={"profile_id": "crew-demo-02", "generate_explanation": False})
    alerts = client.get("/api/v1/profiles/crew-demo-02/alerts?state=open").json()["alerts"]
    assert sum(1 for a in alerts if a["severity"] == "MONITOR") <= 1
    keys = [(a["severity"], a["title"]) for a in alerts]
    assert len(keys) == len(set(keys))
    assert any(a["occurrences"] >= 2 for a in alerts if a["severity"] == "REVIEW")


def test_flaw11_no_spurious_conflicts_on_seeded_profiles(client):
    for p in ("crew-demo-01", "crew-demo-02", "crew-demo-03"):
        client.post(f"/api/v1/profiles/{p}/reset?confirm=true", headers=ADMIN)
        run = client.get(f"/api/v1/profiles/{p}/overview").json()["latest_run"]
        assert not [f for f in run["assessment"]["findings"] if f["code"] == "AGENT_CONFLICT"], p


def test_flaw12_checkin_completes_checkin_task(client):
    sub(client, P1, [obs("mood", 4, "score")])
    today = client.get(f"/api/v1/profiles/{P1}/tasks").json()["today"]
    assert next(t for t in today if t["category"] == "checkin")["completed_at"]


def test_flaw13_one_explanation_at_a_time_and_recovery(client, db):
    from app.orchestration.orchestrator import recover_interrupted_explanations
    run_id = client.get(f"/api/v1/profiles/{P1}/overview").json()["latest_run"]["run_id"]
    with db.transaction() as conn:
        conn.execute("UPDATE analysis_runs SET explanation_status = 'running' WHERE run_id = ?", (run_id,))
    assert client.post(f"/api/v1/analysis-runs/{run_id}/explain").status_code == 409
    assert recover_interrupted_explanations(db) >= 1
    assert client.get(f"/api/v1/analysis-runs/{run_id}").json()["explanation_status"] == "unavailable"


def test_flaw14_destructive_actions_need_admin_pin(client):
    assert client.post("/api/v1/demo/reseed?confirm=true").status_code == 403
    assert client.post("/api/v1/profiles/crew-demo-01/reset?confirm=true", headers={"X-Admin-PIN": "999999"}).status_code == 403
    assert client.post("/api/v1/knowledge/rebuild").status_code == 403


def test_flaw15_browser_restricted_to_local_server(client):
    csp = client.get("/api/v1/system/health").headers["Content-Security-Policy"]
    assert "connect-src 'self'" in csp and "default-src 'self'" in csp


def test_flaw16_encrypted_export_roundtrip_and_pdf(client):
    from app.services.exporting import decrypt
    rep = client.post("/api/v1/reports", json={"profile_id": P1}).json()
    pdf = client.get(f"/api/v1/reports/{rep['report_id']}/export.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-1.4") and pdf.content.rstrip().endswith(b"%%EOF")
    enc = client.post(f"/api/v1/reports/{rep['report_id']}/export.enc", json={"format": "pdf", "passphrase": "orbit-medic-2026"})
    assert enc.status_code == 200 and b"%PDF" not in enc.content
    assert decrypt(enc.content, "orbit-medic-2026").startswith(b"%PDF")
    with pytest.raises(ValueError):
        decrypt(enc.content, "wrong-passphrase")


def test_flaw17_csv_import_and_device_adapter(client):
    base = utcnow() - timedelta(days=90)
    rows = ["metric_code,value,unit,measured_at,context"]
    for i in range(5):
        rows.append(f"heart_rate,{60 + i},bpm,{iso(base + timedelta(days=i))},resting")
    rows += ["heart_rate,abc,bpm,2026-01-01T00:00:00Z,", "bp_systolic,120,mmHg,2026-01-02T00:00:00Z,"]
    res = client.post("/api/v1/imports", json={"profile_id": P1, "format": "csv", "content": "\n".join(rows)}, headers=ADMIN).json()
    assert res["accepted"] == 5 and len(res["rejected"]) == 2 and res["checkin_id"]
    imported = client.get(f"/api/v1/checkins/{res['checkin_id']}").json()["observations"]
    assert all(o["quality_status"] == "valid" for o in imported)  # historical: not "stale"
    rec = {"profile_id": P1, "records": [{"metric_code": "heart_rate", "value": 64, "unit": "bpm",
                                          "measured_at": now_iso(), "context": "resting"}]}
    assert client.post("/api/v1/devices/wrist-01/records", json=rec).status_code == 401  # no token
    tok = {"X-Device-Token": "test-device-token"}
    dev = client.post("/api/v1/devices/wrist-01/records", json=rec, headers=tok).json()
    assert dev["accepted"] == 1 and dev["run_id"]
    bad = {"profile_id": P1, "records": [{"metric_code": "symptom", "value": "chest_pain", "unit": "code", "measured_at": now_iso()}]}
    assert client.post("/api/v1/devices/wrist-01/records", json=bad, headers=tok).status_code == 422


def test_care_plan_recommends_improvements_and_can_be_adopted(client):
    client.post("/api/v1/profiles/crew-demo-02/reset?confirm=true", headers=ADMIN)
    plan = client.get("/api/v1/profiles/crew-demo-02/care-plan").json()
    ids = {i["plan_id"] for i in plan["items"]}
    assert {"sleep", "wellbeing", "exercise"} <= ids
    sleep = next(i for i in plan["items"] if i["plan_id"] == "sleep")
    assert sleep["steps"] and "usual range" in sleep["goal"] and "h" in sleep["goal"]
    text = " ".join(s for i in plan["items"] for s in i["steps"]).lower()
    assert not any(w in text for w in ("medication", "mg", "diagnos", "pill"))
    created = client.post("/api/v1/profiles/crew-demo-02/care-plan/sleep/adopt").json()["created"]
    assert created == 3
    assert client.post("/api/v1/profiles/crew-demo-02/care-plan/sleep/adopt").json()["created"] == 0  # idempotent


def test_no_self_care_plan_in_urgent_state(client):
    client.post(f"/api/v1/profiles/{P3}/reset?confirm=true", headers=ADMIN)
    sub(client, P3, [obs("symptom", "chest_pain", "code")])
    plan = client.get(f"/api/v1/profiles/{P3}/care-plan").json()
    assert plan["items"] == [] and "medical officer" in plan["message"]


def test_findings_carry_certainty_with_reasons(client):
    client.post("/api/v1/profiles/crew-demo-02/reset?confirm=true", headers=ADMIN)
    run = client.get("/api/v1/profiles/crew-demo-02/overview").json()["latest_run"]
    graded = [f for f in run["assessment"]["findings"] if f["severity"] != "INFO" and f["certainty"]]
    assert graded and all(f["certainty_reasons"] for f in graded)
    hr = next(f for f in graded if f["code"] == "HR_BASELINE_DEVIATION")
    assert hr["certainty"] in ("strong", "moderate")


def test_llm_limitations_and_recommendations_must_be_grounded():
    from app.safety.llm_guard import validate_explanation
    findings = [{"code": "SLEEP_SHORT_PATTERN", "severity": "MONITOR", "summary": "Short sleep on 4 of 5 nights.",
                 "limitations": ["Duration only; sleep quality and timing need separate review."],
                 "next_steps": ["Protect the next scheduled sleep period and discuss the pattern at the next medical check-in."]}]
    def check(t, text):
        return validate_explanation({"statements": [{"type": t, "text": text, "finding_codes": ["SLEEP_SHORT_PATTERN"]}]},
                                    findings, [], "MONITOR")["accepted"]
    assert not check("limitation", "The system does not allow averaging conflicting results, which may cause missed trends.")
    assert check("limitation", "This looks at sleep duration only; sleep quality and timing need separate review.")
    assert not check("recommendation", "Try a new supplement before bed.")
    assert check("recommendation", "Protect your next scheduled sleep period and discuss the pattern at the next medical check-in.")
