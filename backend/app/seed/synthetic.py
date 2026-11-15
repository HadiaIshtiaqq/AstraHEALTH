"""Synthetic demo data: one fictional mission, three fictional crew profiles.

All values are generated (seeded RNG) and labelled synthetic. They are examples,
not reference values. Scenarios (test plan 5.6):
  crew-demo-01  Healthy baseline — stable measurements, completed routine
  crew-demo-02  Gradual multi-signal change — sleep, mood, stress, exercise and HR drift over 7 days
  crew-demo-03  Potential urgent event — stable history; the scripted check-in reports urgent symptoms
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

import numpy as np

from app.db.database import Database, bulk_load, dumps, iso, utcnow
from app.schemas.models import CheckinIn, ObservationIn
from app.services import repository as repo
from app.services.checkins import create_checkin
from app.services.tasks import ensure_tasks

MISSION_ID = "ARES-01"
HISTORY_DAYS = 41  # mission day 42 is "today"

PROFILES = [
    {"profile_id": "crew-demo-01", "display_name": "AST-001 · Crew Alpha", "role": "Commander (synthetic)",
     "scenario": "healthy_baseline", "seed": 11,
     "base": {"hr": 61, "sys": 117, "dia": 75, "temp": 36.7, "sleep": 7.3, "mood": 4, "stress": 2, "fatigue": 2,
              "fluid": 2400, "exercise": 128, "mass": 71.5, "appetite": 4}},
    {"profile_id": "crew-demo-02", "display_name": "AST-002 · Crew Bravo", "role": "Flight Engineer (synthetic)",
     "scenario": "gradual_multi_signal_change", "seed": 22,
     "base": {"hr": 59, "sys": 121, "dia": 78, "temp": 36.6, "sleep": 7.1, "mood": 4, "stress": 2, "fatigue": 2,
              "fluid": 2300, "exercise": 124, "mass": 78.2, "appetite": 4}},
    {"profile_id": "crew-demo-03", "display_name": "AST-003 · Crew Charlie", "role": "Mission Specialist (synthetic)",
     "scenario": "potential_urgent_event", "seed": 33,
     "base": {"hr": 64, "sys": 114, "dia": 72, "temp": 36.8, "sleep": 7.0, "mood": 4, "stress": 2, "fatigue": 2,
              "fluid": 2200, "exercise": 120, "mass": 64.0, "appetite": 4}},
]


def _scale(rng: np.random.Generator, center: float, sd: float = 0.35) -> int:
    return int(np.clip(round(rng.normal(center, sd)), 1, 5))


def day_observations(base: dict, rng: np.random.Generator, day_index: int, measured_at: str, drift: float = 0.0,
                     missing: set[str] | None = None) -> list[ObservationIn]:
    """drift in [0,1]: 0 = baseline, 1 = full gradual-change scenario."""
    missing = missing or set()
    b = base
    vals = {
        "heart_rate": (round(rng.normal(b["hr"] + 12 * drift, 2.2)), "bpm"),
        "bp_systolic": (round(rng.normal(b["sys"] + 4 * drift, 3.5)), "mmHg"),
        "bp_diastolic": (round(rng.normal(b["dia"] + 2 * drift, 2.5)), "mmHg"),
        "body_temperature": (round(rng.normal(b["temp"], 0.12), 1), "°C"),
        "sleep_duration": (round(max(2.5, rng.normal(b["sleep"] - 2.3 * drift, 0.35)), 1), "h"),
        "sleep_quality": (_scale(rng, 4 - 2 * drift), "score"),
        "mood": (_scale(rng, b["mood"] - 2.2 * drift, 0.35), "score"),
        "stress": (_scale(rng, b["stress"] + 2.2 * drift, 0.35), "score"),
        "fatigue": (_scale(rng, b["fatigue"] + 2.2 * drift, 0.35), "score"),
        "appetite": (_scale(rng, b["appetite"] - 1.2 * drift, 0.35), "score"),
        "fluid_intake": (int(round(rng.normal(b["fluid"] - 500 * drift, 160), -1)), "mL"),
        "exercise_duration": (int(round(max(0, rng.normal(b["exercise"] - 65 * drift, 9)))), "min"),
        "resistance_exercise": (int(rng.random() > (0.08 + 0.55 * drift)), "bool"),
        "radiation_dose": (round(float(rng.normal(0.52, 0.03)), 3), "mSv"),
    }
    if day_index % 3 == 0:
        vals["body_mass"] = (round(rng.normal(b["mass"] - 0.6 * drift, 0.15), 1), "kg")
    obs = []
    for code, (value, unit) in vals.items():
        if code in missing:
            continue
        obs.append(ObservationIn(metric_code=code, value=value, unit=unit, measured_at=measured_at, source="simulated",
                                 method="synthetic_generator_v1", context="resting" if code == "heart_rate" else None))
    return obs


def ensure_mission(db: Database) -> None:
    start = utcnow().date() - timedelta(days=HISTORY_DAYS)
    with db.transaction() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO mission_contexts VALUES (?,?,?,?,?,?,?,?)",
            (MISSION_ID, "ARES-01 (fictional)", "Mars transit habitat (simulated)", iso(datetime.combine(start, time(6, 0), timezone.utc)),
             "microgravity", "delayed (simulated 8–20 min one-way)", 540, 1),
        )


def seed_profile(db: Database, spec: dict, run_initial_analysis: bool = True) -> None:
    from app.orchestration.orchestrator import run_analysis  # local import avoids a cycle

    rng = np.random.default_rng(spec["seed"])
    now = utcnow()
    with db.transaction() as conn:
        conn.execute("DELETE FROM crew_profiles WHERE profile_id = ?", (spec["profile_id"],))
        conn.execute(
            "INSERT INTO crew_profiles VALUES (?,?,?,?,?,?,?,?,?,?)",
            (spec["profile_id"], spec["display_name"], spec["role"], MISSION_ID, dumps({}),
             dumps({"exercise_target_min": 120, "resistance_sessions_per_week": 6, "temperature_unit": "°C",
                    "display_timezone": "UTC", "llm_explanations": True}),
             "UTC", spec["scenario"], 1, iso(now)),
        )
    last_checkin = None
    today = now.date()
    for i in range(HISTORY_DAYS):
        day = today - timedelta(days=HISTORY_DAYS - i)
        if spec["scenario"] == "healthy_baseline" and i == 20:
            continue  # one missed check-in day to show a data gap
        measured = datetime.combine(day, time(7, 30), timezone.utc)
        drift = 0.0
        missing: set[str] = set()
        if spec["scenario"] == "gradual_multi_signal_change":
            days_from_end = HISTORY_DAYS - 1 - i
            drift = max(0.0, (7 - days_from_end) / 7) if days_from_end < 7 else 0.0
            if i in (HISTORY_DAYS - 4,):
                missing = {"exercise_duration", "resistance_exercise"}
        obs = day_observations(spec["base"], rng, i, iso(measured), drift, missing)
        payload = CheckinIn(profile_id=spec["profile_id"], observations=obs, mode="simulated", run_analysis=False)
        last_checkin = create_checkin(db, payload, is_synthetic=True, submitted_at=measured + timedelta(minutes=4), audit=False)
        ensure_tasks(db, spec["profile_id"], day)
        _complete_seeded_tasks(db, spec["profile_id"], day, obs, measured)
    ensure_tasks(db, spec["profile_id"], today)
    if run_initial_analysis and last_checkin:
        run_analysis(db, spec["profile_id"], last_checkin, generate_explanation=False)


def _complete_seeded_tasks(db: Database, profile_id: str, day, obs: list[ObservationIn], measured: datetime) -> None:
    values = {o.metric_code: o.value for o in obs}
    done = {"Morning health check-in": True,
            "Aerobic exercise session": (values.get("exercise_duration") or 0) >= 30,
            "Resistance exercise session": values.get("resistance_exercise") == 1,
            "Log fluid intake": "fluid_intake" in values,
            "Pre-sleep light routine": (values.get("sleep_quality") or 0) >= 3,
            "Private family call": True}
    with db.transaction() as conn:
        for title, completed in done.items():
            if completed:
                conn.execute("UPDATE tasks SET completed_at = ?, completion_note = 'synthetic history' "
                             "WHERE profile_id = ? AND scheduled_for = ? AND title = ?",
                             (iso(measured + timedelta(hours=10)), profile_id, day.isoformat(), title))


def seed_all(db: Database, force: bool = False) -> bool:
    existing = db.one("SELECT COUNT(*) AS n FROM crew_profiles")
    if existing and existing["n"] and not force:
        return False
    ensure_mission(db)
    with bulk_load():
        for spec in PROFILES:
            seed_profile(db, spec)
    repo.audit(db, "demo.seeded", None, actor_role="admin", profiles=len(PROFILES))
    return True


def reset_profile(db: Database, profile_id: str) -> None:
    spec = next((p for p in PROFILES if p["profile_id"] == profile_id), None)
    with db.transaction() as conn:
        conn.execute("DELETE FROM crew_profiles WHERE profile_id = ?", (profile_id,))
    if spec:
        ensure_mission(db)
        with bulk_load():
            seed_profile(db, spec)
    repo.audit(db, "demo.profile_reset", profile_id, actor_role="admin")


# ---------------------------------------------------------------- scripted demo check-ins
def scenario_checkin(scenario: str) -> CheckinIn:
    now = iso(utcnow())
    def o(code, value, unit, **kw):
        return ObservationIn(metric_code=code, value=value, unit=unit, measured_at=now, source="manual", **kw)

    if scenario == "healthy":
        return CheckinIn(profile_id="crew-demo-01", mode="manual", observations=[
            o("heart_rate", 62, "bpm", context="resting"), o("bp_systolic", 118, "mmHg"), o("bp_diastolic", 76, "mmHg"),
            o("body_temperature", 36.7, "°C"), o("sleep_duration", 7.4, "h"), o("sleep_quality", 4, "score"),
            o("mood", 4, "score"), o("stress", 2, "score"), o("fatigue", 2, "score"), o("fluid_intake", 2350, "mL"),
            o("exercise_duration", 125, "min"), o("resistance_exercise", 1, "bool")])
    if scenario == "gradual":
        return CheckinIn(profile_id="crew-demo-02", mode="manual", observations=[
            o("heart_rate", 72, "bpm", context="resting"), o("bp_systolic", 125, "mmHg"), o("bp_diastolic", 80, "mmHg"),
            o("sleep_duration", 4.9, "h"), o("sleep_quality", 2, "score"), o("mood", 2, "score"), o("stress", 4, "score"),
            o("fatigue", 4, "score"), o("fluid_intake", 1750, "mL"), o("exercise_duration", 55, "min"),
            o("resistance_exercise", 0, "bool"), o("appetite", 3, "score")])
    if scenario == "urgent":
        return CheckinIn(profile_id="crew-demo-03", mode="manual", notes="Scripted demo: potential urgent event",
                         observations=[
            o("heart_rate", 97, "bpm", context="resting"), o("bp_systolic", 112, "mmHg"), o("bp_diastolic", 70, "mmHg"),
            o("symptom", "shortness_of_breath", "code"), o("symptom", "dizziness", "code"), o("symptom", "chest_pain", "code"),
            o("sleep_duration", 6.8, "h"), o("mood", 3, "score"), o("stress", 4, "score"), o("fatigue", 3, "score")])
    raise KeyError(scenario)


SCENARIOS = {
    "healthy": {"label": "Healthy baseline check-in", "profile_id": "crew-demo-01"},
    "gradual": {"label": "Gradual multi-signal change", "profile_id": "crew-demo-02"},
    "urgent": {"label": "Potential urgent event", "profile_id": "crew-demo-03"},
    "agent_failure": {"label": "Agent failure (SleepSense fault injected)", "profile_id": "crew-demo-01"},
}



# ---------------------------------------------------------------- keep the demo timeline current
_TS_COLUMNS = [
    ("mission_contexts", "mission_start"), ("checkins", "submitted_at"), ("observations", "measured_at"),
    ("observations", "recorded_at"), ("analysis_runs", "started_at"), ("analysis_runs", "completed_at"),
    ("alerts", "created_at"), ("alerts", "last_seen_at"), ("alerts", "acknowledged_at"), ("tasks", "completed_at"),
    ("reports", "window_start"), ("reports", "window_end"), ("reports", "created_at"),
]


def shift_demo_clock(db: Database) -> int:
    """Move the whole synthetic timeline forward so seeded history always ends yesterday.

    Without this, a demo given days after seeding shows stale data and weakened trends. Only the synthetic
    demo profiles are moved; real profiles added by the user are never touched. Relative structure, IDs and
    the audit history are unchanged.
    """
    synthetic = [r["profile_id"] for r in db.query("SELECT profile_id FROM crew_profiles WHERE is_synthetic = 1")]
    if not synthetic:
        return 0
    marks = ",".join("?" * len(synthetic))
    row = db.one(f"SELECT MAX(submitted_at) AS last FROM checkins WHERE mode = 'simulated' AND profile_id IN ({marks})", synthetic)
    if not row or not row["last"]:
        return 0
    from app.db.database import parse_iso
    days = (utcnow().date() - parse_iso(row["last"]).date()).days - 1
    if days < 1:
        return 0
    shift = f"+{days} days"
    with db.transaction() as conn:
        for table, col in _TS_COLUMNS:
            if table == "mission_contexts":  # only the fictional demo mission moves; real profiles never use it
                conn.execute(f"UPDATE {table} SET {col} = strftime('%Y-%m-%dT%H:%M:%SZ', replace({col}, 'Z', ''), ?) "
                             "WHERE mission_id = ?", (shift, MISSION_ID))
                continue
            conn.execute(f"UPDATE {table} SET {col} = strftime('%Y-%m-%dT%H:%M:%SZ', replace({col}, 'Z', ''), ?) "
                         f"WHERE {col} IS NOT NULL AND profile_id IN ({marks})", (shift, *synthetic))
        conn.execute(f"UPDATE tasks SET scheduled_for = date(scheduled_for, ?) WHERE profile_id IN ({marks})", (shift, *synthetic))
    repo.audit(db, "demo.clock_shifted", None, actor_role="system", days=days)
    return days
