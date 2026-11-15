"""Regression tests for the fifth review round."""
from tests.conftest import ADMIN


def test_real_profile_has_no_fictional_mission(client):
    p = client.post("/api/v1/profiles", json={"display_name": "Real crew R5", "timezone": "UTC"}).json()
    assert p["mission_id"] == "NONE" and p["has_mission"] is False and p["mission_day"] is None
    assert p["is_synthetic"] is False
    from app.agents.base import AgentContext
    from app.agents.mission_context import MissionContextAgent
    from app.db.database import get_db, utcnow
    from app.services.repository import get_profile
    prof = get_profile(get_db(), p["profile_id"])
    ctx = AgentContext(run_id="t", profile=prof, reference_time=utcnow(), checkin_id=None,
                       checkin_observations=(), history=())
    mc = MissionContextAgent().analyze(ctx).model_dump()
    codes = [f["code"] for f in mc["findings"]]
    assert "COMM_DELAY_NOTE" not in codes
    summary = next(f for f in mc["findings"] if f["code"] == "MISSION_CONTEXT_SUMMARY")["summary"]
    assert "No mission is assigned" in summary and "ARES" not in summary
    client.delete(f"/api/v1/profiles/{p['profile_id']}?confirm=true", headers=ADMIN)


def test_demo_profiles_keep_their_mission(client):
    p = client.get("/api/v1/profiles/crew-demo-01").json()
    assert p["has_mission"] is True and p["mission_day"] >= 1


def test_initial_secrets_file_can_be_deleted_by_admin(client):
    from app.core.security import initial_secrets_path
    path = initial_secrets_path()
    path.write_text("test", encoding="utf-8")
    assert client.post("/api/v1/system/initial-secrets/delete").status_code == 403
    assert path.exists()
    r = client.post("/api/v1/system/initial-secrets/delete", headers=ADMIN).json()
    assert r["deleted"] is True and not path.exists()


def test_model_is_unloaded_quickly_on_low_memory(monkeypatch):
    from app.intelligence import local_llm
    monkeypatch.setattr(local_llm, "free_ram_gb", lambda: 2.0)
    assert local_llm.should_keep_loaded() is False and local_llm.keep_alive() == "1m"
    monkeypatch.setattr(local_llm, "free_ram_gb", lambda: 12.0)
    assert local_llm.keep_alive() == "30m"
