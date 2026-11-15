"""Countermeasure tasks. Completion is always an explicit user action (never inferred)."""
from __future__ import annotations

from datetime import date, timedelta

from app.db.database import Database, iso, new_id, utcnow
from app.ml.stats import zone
from app.services import repository as repo

DAILY_TASKS = [
    ("Morning health check-in", "checkin", "Record vital signs, sleep and wellbeing for today."),
    ("Aerobic exercise session", "exercise", "Treadmill or cycle ergometer session per the countermeasure plan."),
    ("Resistance exercise session", "exercise", "Resistance device session per the countermeasure plan."),
    ("Log fluid intake", "nutrition", "Log all fluid intake for the day."),
    ("Pre-sleep light routine", "sleep", "Dim lighting and screens before the scheduled sleep period."),
]
WEEKLY_TASKS = [
    ("Private family call", "wellbeing", "Scheduled private communication window.", 6),  # weekday index (Sunday)
]


def ensure_tasks(db: Database, profile_id: str, day: date) -> None:
    existing = db.one("SELECT COUNT(*) AS n FROM tasks WHERE profile_id = ? AND scheduled_for = ?",
                      (profile_id, day.isoformat()))
    if existing and existing["n"]:
        return
    rows = [(new_id("task"), profile_id, t, c, d, day.isoformat(), None, None) for t, c, d in DAILY_TASKS]
    rows += [(new_id("task"), profile_id, t, c, d, day.isoformat(), None, None)
             for t, c, d, wd in WEEKLY_TASKS if day.weekday() == wd]
    with db.transaction() as conn:
        conn.executemany("INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?)", rows)


def local_today(db: Database, profile_id: str) -> date:
    row = db.one("SELECT timezone FROM crew_profiles WHERE profile_id = ?", (profile_id,))
    return utcnow().astimezone(zone(row["timezone"] if row else "UTC")).date()


def complete_checkin_task(db: Database, profile: dict, submitted) -> None:
    """Submitting a check-in is an explicit action by the crew member, so it completes the check-in task."""
    day = submitted.astimezone(zone(profile.get("timezone") or "UTC")).date()
    ensure_tasks(db, profile["profile_id"], day)
    with db.transaction() as conn:
        conn.execute("UPDATE tasks SET completed_at = ?, completion_note = 'Completed by submitting a check-in' "
                     "WHERE profile_id = ? AND scheduled_for = ? AND category = 'checkin' AND completed_at IS NULL",
                     (iso(submitted), profile["profile_id"], day.isoformat()))


def add_plan_tasks(db: Database, profile_id: str, item: dict) -> int:
    """Add a care-plan task to today and the following days; skips days that already have it."""
    today = local_today(db, profile_id)
    title = f"{item['task']['title']} (care plan)"
    created = 0
    with db.transaction() as conn:
        for i in range(item["task"]["days"]):
            day = (today + timedelta(days=i)).isoformat()
            exists = conn.execute("SELECT 1 FROM tasks WHERE profile_id = ? AND scheduled_for = ? AND title = ?",
                                  (profile_id, day, title)).fetchone()
            if not exists:
                conn.execute("INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?)",
                             (new_id("task"), profile_id, title, item["task"]["category"],
                              f"{item['title']}: {item['steps'][0]}", day, None, None))
                created += 1
    repo.audit(db, "careplan.adopted", item["plan_id"], actor_role="crew", tasks=created)
    return created


def list_tasks(db: Database, profile_id: str, days: int = 7) -> dict:
    today = local_today(db, profile_id)
    ensure_tasks(db, profile_id, today)
    start = (today - timedelta(days=days - 1)).isoformat()
    rows = db.query("SELECT * FROM tasks WHERE profile_id = ? AND scheduled_for >= ? ORDER BY scheduled_for DESC, category, title",
                    (profile_id, start))
    today_rows = [r for r in rows if r["scheduled_for"] == today.isoformat()]
    history: dict[str, dict] = {}
    for r in rows:
        h = history.setdefault(r["scheduled_for"], {"date": r["scheduled_for"], "total": 0, "completed": 0})
        h["total"] += 1
        h["completed"] += 1 if r["completed_at"] else 0
    # Streak of consecutive days (ending yesterday or today) with the check-in task completed.
    streak = 0
    for i in range(0, 60):
        d = (today - timedelta(days=i)).isoformat()
        row = db.one("SELECT completed_at FROM tasks WHERE profile_id = ? AND scheduled_for = ? AND category = 'checkin'",
                     (profile_id, d))
        if row and row["completed_at"]:
            streak += 1
        elif i == 0:
            continue
        else:
            break
    return {"today": today_rows, "history": sorted(history.values(), key=lambda h: h["date"]), "checkin_streak": streak}


def complete_task(db: Database, task_id: str, note: str | None) -> dict:
    task = db.one("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
    if task is None:
        raise LookupError("Task not found")
    if not task["completed_at"]:
        with db.transaction() as conn:
            conn.execute("UPDATE tasks SET completed_at = ?, completion_note = ? WHERE task_id = ?",
                         (iso(utcnow()), note, task_id))
        repo.audit(db, "task.completed", task_id, actor_role="crew", category=task["category"])
    return db.one("SELECT * FROM tasks WHERE task_id = ?", (task_id,))  # type: ignore[return-value]


def undo_task(db: Database, task_id: str) -> dict:
    with db.transaction() as conn:
        conn.execute("UPDATE tasks SET completed_at = NULL, completion_note = NULL WHERE task_id = ?", (task_id,))
    repo.audit(db, "task.reopened", task_id, actor_role="crew")
    return db.one("SELECT * FROM tasks WHERE task_id = ?", (task_id,))  # type: ignore[return-value]


def remove_task(db: Database, task_id: str) -> dict:
    """Care-plan tasks the crew member added can be removed again (routine tasks cannot)."""
    task = db.one("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
    if task is None:
        raise LookupError("Task not found")
    if not task["title"].endswith("(care plan)"):
        raise ValueError("Only tasks added from the care plan can be removed.")
    if task["completed_at"]:
        raise ValueError("Completed tasks stay in the record.")
    with db.transaction() as conn:
        conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
    repo.audit(db, "task.removed", task_id, actor_role="crew")
    return {"removed": task_id}
