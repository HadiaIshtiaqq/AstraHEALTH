"""Care plan: what the crew member can do to improve each detected condition.

Deterministic and versioned. Recommendations are routine countermeasures and self-monitoring
steps drawn from the local knowledge library — never medication, diagnosis or treatment.
Goals are expressed relative to the crew member's *own* baseline, so no population
thresholds are invented. URGENT states get no self-care plan: the only action is the
medical officer.
"""
from __future__ import annotations

from typing import Any

CARE_PLAN_VERSION = "care-1.0.0"

# Plan templates keyed by plan id; finding codes map onto plans below.
PLANS: dict[str, dict[str, Any]] = {
    "sleep": {
        "title": "Protect and rebuild sleep",
        "area": "Sleep", "category": "sleep",
        "why": "Repeated short sleep affects alertness, mood and performance; fatigue reports are easier to interpret with sleep logged.",
        "steps": [
            "Keep the same scheduled sleep window for the next 3 nights.",
            "Dim lighting and screens for 60 minutes before the sleep period.",
            "Use the sleep-station aids (eye mask, ear plugs, temperature) to reduce noise and light.",
            "Avoid late-day caffeine and heavy workload right before sleep where the timeline allows.",
            "Log sleep duration and quality each morning.",
        ],
        "goal": "Sleep back within your usual range ({usual}) for 3 nights in a row.",
        "task": "Protected sleep window", "task_days": 3, "evidence": "KB-003-C04",
    },
    "wellbeing": {
        "title": "Recovery and connection",
        "area": "Wellbeing", "category": "wellbeing",
        "why": "Isolation and confinement can shift mood, stress and fatigue gradually; routines, connection and support help.",
        "steps": [
            "Schedule a private call or message window with family or friends this week.",
            "Take a 10-minute decompression break daily (breathing, music, a view of Earth).",
            "Protect planned leisure time in the timeline.",
            "Keep doing the daily check-in so changes are visible early.",
            "A private conversation with the crew medical officer is available at any time.",
        ],
        "goal": "Stress and fatigue back to your usual scores ({usual}) over the next 5 check-ins.",
        "task": "10-minute decompression break", "task_days": 5, "evidence": "KB-004-C03",
    },
    "cardio_recheck": {
        "title": "Re-check under standard conditions",
        "area": "Heart & circulation", "category": "checkin",
        "why": "Heart rate and blood pressure vary with posture, recent exercise, stress, caffeine and sleep, so one reading is hard to interpret.",
        "steps": [
            "Repeat the measurement seated and at rest, before exercise, at the same time of day.",
            "Record the measurement context (resting or post-exercise) every time.",
            "Check whether sleep, stress or fluid logs also changed in the same days.",
            "If it stays away from your usual range, share the trend with the medical officer.",
        ],
        "goal": "Three resting readings with context recorded; values back within your usual range ({usual}).",
        "task": "Resting vital-sign re-check", "task_days": 3, "evidence": "KB-002-C03",
    },
    "exercise": {
        "title": "Rebuild the countermeasure routine",
        "area": "Bones & muscles", "category": "exercise",
        "why": "Consistent exercise, including resistance sessions, is one of the main countermeasures for bone and muscle loss.",
        "steps": [
            "Block fixed exercise slots in the timeline for the next 7 days.",
            "If a full session does not fit, split it into two shorter sessions.",
            "Prioritise the scheduled resistance sessions.",
            "Tell the exercise specialist if discomfort or fatigue is limiting sessions.",
        ],
        "goal": "At least {target} of the planned exercise minutes over the next 7 days.",
        "task": "Planned exercise session", "task_days": 7, "evidence": "KB-005-C02",
    },
    "msk": {
        "title": "Look after the discomfort",
        "area": "Bones & muscles", "category": "exercise",
        "why": "Back and joint discomfort is common in flight; persistent discomfort that limits exercise needs review.",
        "steps": [
            "Note where it hurts and which activity triggers it.",
            "Warm up before resistance sessions and check device set-up and posture.",
            "Tell the medical officer or exercise specialist if it persists or limits exercise.",
        ],
        "goal": "Discomfort back to your usual level, with exercise not limited.",
        "task": "Log discomfort and trigger", "task_days": 3, "evidence": "KB-005-C04",
    },
    "fluid": {
        "title": "Complete and steady intake logging",
        "area": "Nutrition", "category": "nutrition",
        "why": "Logged intake is only meaningful when the log is complete; a low total can simply be an unfinished log.",
        "steps": [
            "Log every drink as you have it rather than at the end of the day.",
            "Spread intake through the day according to the mission nutrition plan.",
            "Check the log is complete before the evening check-in.",
        ],
        "goal": "Complete daily logs, with totals back within your usual range ({usual}).",
        "task": "Complete fluid log", "task_days": 3, "evidence": "KB-006-C02",
    },
    "nutrition": {
        "title": "Appetite and meal tracking",
        "area": "Nutrition", "category": "nutrition",
        "why": "Appetite changes with workload, stress, sleep and menu fatigue; tracking separates a short dip from a trend.",
        "steps": [
            "Log meals for the next 3 days.",
            "Ask the nutrition team about menu variety if food fatigue is a factor.",
            "Repeat body-mass measurement using the standard procedure.",
        ],
        "goal": "Appetite and body mass back within your usual range ({usual}).",
        "task": "Meal log", "task_days": 3, "evidence": "KB-006-C04",
    },
    "remeasure": {
        "title": "Confirm the measurement",
        "area": "Data quality", "category": "checkin",
        "why": "An unusual value may be real or a measurement problem; repeating it under standard conditions settles which.",
        "steps": ["Repeat the measurement with the same device and method.", "Confirm or correct the flagged value in Health Trends."],
        "goal": "Flagged value confirmed or corrected.",
        "task": "Repeat flagged measurement", "task_days": 1, "evidence": "KB-008-C01",
    },
}

FINDING_TO_PLAN = {
    "SLEEP_SHORT_PATTERN": "sleep", "SLEEP_BELOW_BASELINE": "sleep",
    "WELLBEING_MULTI_SIGNAL_DECLINE": "wellbeing", "WELLBEING_TREND_ADVERSE": "wellbeing", "WELLBEING_SINGLE_DAY_CHANGE": "wellbeing",
    "HR_BASELINE_DEVIATION": "cardio_recheck", "BP_BASELINE_DEVIATION": "cardio_recheck", "TEMP_BASELINE_DEVIATION": "cardio_recheck",
    "EXERCISE_ADHERENCE_BELOW_PLAN": "exercise", "RESISTANCE_SESSIONS_MISSED": "exercise",
    "MSK_DISCOMFORT_REPORTED": "msk",
    "FLUID_INTAKE_BELOW_BASELINE": "fluid",
    "APPETITE_BELOW_BASELINE": "nutrition", "BODY_MASS_CHANGE": "nutrition",
    "DATA_QUALITY_FLAG": "remeasure",
}
SEV_ORDER = {"URGENT": 0, "REVIEW": 1, "MONITOR": 2, "INFO": 3}


def _usual(findings: list[dict], baselines: dict, metric_codes: list[str]) -> str:
    parts = []
    for code in metric_codes:
        b = baselines.get(code) or {}
        if b.get("available") and b.get("p10") is not None:
            unit = b.get("unit", "")
            lo, hi = b["p10"], b["p90"]
            name = b["label"].split(" (")[0].lower()
            if unit == "score":
                parts.append(f"{name} {lo:g}/5" if lo == hi else f"{name} {lo:g}–{hi:g}/5")
            else:
                digits = 1 if unit in ("h", "°C", "kg") else 0
                rng = f"{lo:.{digits}f}" if round(lo, digits) == round(hi, digits) else f"{lo:.{digits}f}–{hi:.{digits}f}"
                parts.append(f"{name} {rng} {unit}")
    return "; ".join(parts) or "your personal usual range"


def build_care_plan(assessment: dict, baselines: dict, profile_settings: dict) -> dict:
    state = assessment.get("monitoring_state")
    if state == "URGENT":
        return {"version": CARE_PLAN_VERSION, "state": state, "items": [],
                "message": "Urgent state: no self-care plan is offered. Contact the onboard medical officer now and follow the "
                           "mission's emergency procedure. A care plan will be suggested once the urgent alert is assessed."}
    by_plan: dict[str, dict] = {}
    for f in sorted(assessment.get("findings", []), key=lambda f: SEV_ORDER.get(f["severity"], 3)):
        if f["severity"] == "INFO":
            continue
        plan_id = FINDING_TO_PLAN.get(f["code"])
        if plan_id is None and f["code"] in ("MULTIVARIATE_ANOMALY", "CROSS_DOMAIN_PATTERN", "PERSISTENT_CHANGE_DETECTED"):
            continue  # covered by the specialist plans of the contributing signals
        if plan_id is None:
            continue
        entry = by_plan.setdefault(plan_id, {"plan_id": plan_id, "severity": f["severity"], "finding_codes": [], "metric_codes": []})
        entry["finding_codes"].append(f["code"])
        entry["metric_codes"] += [m for m in f.get("metric_codes", []) if m not in entry["metric_codes"] and m != "symptom"]
    items = []
    for plan_id, entry in by_plan.items():
        t = PLANS[plan_id]
        metrics = entry["metric_codes"] or {"wellbeing": ["stress", "fatigue"], "sleep": ["sleep_duration"],
                                            "fluid": ["fluid_intake"], "nutrition": ["appetite", "body_mass"]}.get(plan_id, [])
        goal = t["goal"].format(usual=_usual(assessment.get("findings", []), baselines, metrics), target="80%")
        items.append({
            "plan_id": plan_id, "title": t["title"], "area": t["area"], "severity": entry["severity"],
            "why": t["why"], "steps": t["steps"], "goal": goal, "evidence_chunk": t["evidence"],
            "linked_findings": entry["finding_codes"], "task": {"title": t["task"], "category": t["category"], "days": t["task_days"]},
            "needs_medical_officer": entry["severity"] == "REVIEW",
        })
    items.sort(key=lambda i: SEV_ORDER.get(i["severity"], 3))
    message = ("Routine countermeasures and self-monitoring only — not treatment. "
               + ("Because qualified review is recommended, share this plan with the medical officer." if state == "REVIEW" else ""))
    if not items:
        message = "Nothing to improve right now — keep your routine and daily check-ins."
    return {"version": CARE_PLAN_VERSION, "state": state, "items": items, "message": message.strip()}


# ---------------------------------------------------------------- progress towards each goal
PLAN_METRICS = {"sleep": ["sleep_duration"], "wellbeing": ["stress", "fatigue", "mood"], "cardio_recheck": ["heart_rate"],
                "exercise": ["exercise_duration"], "fluid": ["fluid_intake"], "nutrition": ["appetite", "body_mass"],
                "msk": ["msk_discomfort"]}
# Which side of the usual range counts as "back to usual" (one-sided where higher/lower is the adverse direction).
GOOD_SIDE = {"sleep_duration": "low", "mood": "low", "fluid_intake": "low", "appetite": "low", "exercise_duration": "low",
             "stress": "high", "fatigue": "high", "msk_discomfort": "high", "heart_rate": "both", "body_mass": "both"}


def progress_for(item: dict, history: list[dict], baselines: dict, tz: str, days: int = 3) -> dict:
    """Has the crew member got back to their usual range on the last few days with data?"""
    from app.ml.stats import daily_series

    metrics = [m for m in PLAN_METRICS.get(item["plan_id"], []) if (baselines.get(m) or {}).get("available")]
    if not metrics:
        return {"status": "no_data", "detail": "Progress is tracked once there is a personal baseline for this area."}
    per_metric = []
    for m in metrics:
        b = baselines[m]
        series = list(daily_series(history, m, tz).items())[-days:]
        if not series:
            continue
        side = GOOD_SIDE.get(m, "both")
        def in_usual_range(v: float) -> bool:
            above_floor = v >= b["p10"] if side in ("low", "both") else True
            below_ceiling = v <= b["p90"] if side in ("high", "both") else True
            return above_floor and below_ceiling

        ok = sum(1 for _, v in series if in_usual_range(v))
        per_metric.append((m, ok, len(series)))
    if not per_metric:
        return {"status": "no_data", "detail": "No recent measurements yet — keep logging to see progress."}
    good = sum(ok for _, ok, _ in per_metric)
    total = sum(n for _, _, n in per_metric)
    status = "achieved" if good == total and total >= len(per_metric) * days else "on_track" if good >= total / 2 else "not_yet"
    detail = "; ".join(f"{m.replace('_', ' ')}: {ok} of last {n} day(s) in your usual range" for m, ok, n in per_metric)
    return {"status": status, "detail": detail, "days_ok": good, "days_checked": total}
