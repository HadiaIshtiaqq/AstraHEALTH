"""Regression tests for the fourth review round."""
import json
import time

import pytest

from tests.conftest import ADMIN, now_iso

P1, P2, P3 = "crew-demo-01", "crew-demo-02", "crew-demo-03"


def test_demo_controls_fault_injection_and_imports_need_admin(client):
    assert client.post("/api/v1/demo/scenarios/urgent/run").status_code == 403
    assert client.post("/api/v1/analysis-runs", json={"profile_id": P1, "simulate_failure": ["cardio_guard"]}).status_code == 403
    assert client.post("/api/v1/analysis-runs", json={"profile_id": P1, "generate_explanation": False}).status_code == 201
    csv = "metric_code,value,unit,measured_at\nheart_rate,60,bpm,2026-10-01T07:00:00Z"
    assert client.post("/api/v1/imports", json={"profile_id": P1, "format": "csv", "content": csv}).status_code == 403
    sym = "metric_code,value,unit,measured_at\nsymptom,chest_pain,code,2026-10-01T07:00:00Z"
    r = client.post("/api/v1/imports", json={"profile_id": P1, "format": "csv", "content": sym}, headers=ADMIN)
    assert r.status_code == 422 and "symptom" in r.text


def test_wrong_pins_cause_only_a_short_cooldown(client):
    from app.core import security
    security._failures.clear()
    for i in range(5):
        assert not security.check_pin("medical_officer_pin", f"55555{i}")
    assert 0 < security.lock_status("medical_officer_pin") <= security.COOLDOWN_S  # bounded: at most 60 s
    security._failures["medical_officer_pin"]["until"] = time.time() - 1  # cool-down elapsed
    assert security.check_pin("medical_officer_pin", "111111")  # the real officer gets in again
    security._failures.clear()


def test_pin_failures_are_audited(client, db):
    from app.core import security
    security._failures.clear()
    security.check_pin("admin_pin", "999999")
    assert db.one("SELECT 1 AS x FROM audit_events WHERE action = 'security.pin_failed'")
    security._failures.clear()


def test_all_secret_keys_protected(client):
    from app.core.security import credentials_path
    creds = json.loads(credentials_path().read_text(encoding="utf-8"))
    assert creds["version"] == 3
    assert all("dpapi" in v or "plain" in v for v in creds["secret_keys"].values())
    assert "dpapi" in creds["data_key"] or "plain" in creds["data_key"]


def test_audit_log_is_tamper_evident(client, db):
    client.post("/api/v1/analysis-runs", json={"profile_id": P1, "generate_explanation": False})
    assert client.get("/api/v1/system/audit", headers=ADMIN).json()["chain"]["intact"]
    assert client.get("/api/v1/system/audit").status_code == 403
    with db.transaction() as conn:
        conn.execute("UPDATE audit_events SET action = 'edited' WHERE rowid = (SELECT MAX(rowid) FROM audit_events WHERE hash IS NOT NULL)")
    chain = client.get("/api/v1/system/audit", headers=ADMIN).json()["chain"]
    assert chain["intact"] is False and chain["broken_at"]
    from app.services.repository import _event_hash  # repair for the remaining tests
    rows = db.query("SELECT rowid, * FROM audit_events WHERE hash IS NOT NULL ORDER BY rowid")
    with db.transaction() as conn:
        prev = "0" * 64
        for r in rows:
            h = _event_hash(prev, r["event_id"], r["actor_role"], r["action"], r["object_id"], r["timestamp"], r["metadata"])
            conn.execute("UPDATE audit_events SET prev_hash = ?, hash = ? WHERE rowid = ?", (prev, h, r["rowid"]))
            prev = h


def test_demo_clock_shift_does_not_rewrite_audit(client, db):
    from app.seed.synthetic import shift_demo_clock
    before = db.one("SELECT timestamp FROM audit_events ORDER BY rowid LIMIT 1")["timestamp"]
    with db.transaction() as conn:
        conn.execute("UPDATE checkins SET submitted_at = strftime('%Y-%m-%dT%H:%M:%SZ', replace(submitted_at,'Z',''), '-2 days')")
    assert shift_demo_clock(db) >= 1
    assert db.one("SELECT timestamp FROM audit_events ORDER BY rowid LIMIT 1")["timestamp"] == before
    assert client.get("/api/v1/system/audit", headers=ADMIN).json()["chain"]["intact"]


def test_backups_are_encrypted_and_restorable(client, tmp_path):
    from app.services import backup
    res = backup.make_backup("test")
    if not res["ok"]:
        pytest.skip(res["reason"])
    blob = (backup.backup_dir() / res["file"]).read_bytes()
    assert not blob.startswith(b"SQLite format 3")
    restored = backup.restore_to(res["file"], tmp_path / "restored.db")
    assert restored.read_bytes().startswith(b"SQLite format 3")


def test_guard_blocks_new_clinical_concepts():
    from app.safety.llm_guard import validate_explanation
    findings = [{"code": "SLEEP_SHORT_PATTERN", "severity": "MONITOR", "summary": "4 of the last 5 sleep periods were shorter than usual.",
                 "limitations": [], "next_steps": []}]
    out = validate_explanation({"statements": [{"type": "interpretation", "finding_codes": ["SLEEP_SHORT_PATTERN"],
                                                "text": "Shorter sleep periods than usual can weaken immune function."}]},
                               findings, [], "MONITOR")
    assert not out["accepted"] and "clinical concept" in out["rejected"][0]["reason"]


def test_llm_pipeline_end_to_end_with_stubbed_model(client, db, monkeypatch):
    """The real explanation path (prompt -> model -> guard -> storage) with a stubbed local model."""
    from app.intelligence import local_llm
    from app.orchestration import orchestrator
    run = client.get(f"/api/v1/profiles/{P2}/overview").json()["latest_run"]
    codes = [f["code"] for f in run["assessment"]["findings"] if f["severity"] != "INFO"]
    stub = {"statements": [
        {"type": "recommendation", "text": "Share this report with the onboard medical officer for review.", "finding_codes": codes[:1]},
        {"type": "interpretation", "text": "You probably have a heart problem.", "finding_codes": codes[:1]},
    ]}
    monkeypatch.setattr(local_llm, "generate_json", lambda prompt, system: (stub, {"model": "stub", "latency_ms": 5}))
    orchestrator.generate_explanation_for_run(db, run["run_id"])
    e = client.get(f"/api/v1/analysis-runs/{run['run_id']}").json()["explanation"]
    assert e["status"] == "generated"
    assert any(s["type"] == "recommendation" for s in e["statements"])
    assert any(s["type"] == "limitation" for s in e["statements"])  # always added
    assert any("heart problem" in r["text"] for r in e["rejected"])


def test_concurrent_checkins_are_all_saved(client):
    from concurrent.futures import ThreadPoolExecutor

    def submit(i):
        return client.post("/api/v1/checkins", json={"profile_id": P1, "run_analysis": False, "observations": [
            {"metric_code": "fluid_intake", "value": 100 + i, "unit": "mL", "measured_at": now_iso(), "source": "manual"}]}).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(submit, range(16)))
    assert codes.count(201) == 16
