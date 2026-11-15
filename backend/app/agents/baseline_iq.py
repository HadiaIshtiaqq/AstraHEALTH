"""BaselineIQ — personal baseline per metric (what is usual for *this* crew member)."""
from __future__ import annotations

from datetime import timedelta

from app.agents.base import AgentContext, BaseAgent
from app.domain.metrics import METRICS
from app.ml.stats import ewma, robust_summary, robust_z, slope_per_day
from app.schemas.models import Finding

BASELINE_WINDOW_DAYS = 30
# The most recent days are excluded from the reference so a developing change does not dilute
# its own baseline (sustained-change checks compare exactly these recent days against it).
RECENT_EXCLUDE_DAYS = 3


def confidence_label(n: int) -> str:
    if n >= 21:
        return "high"
    if n >= 14:
        return "moderate"
    return "low"


def compute_baselines(ctx: AgentContext, metric_codes: set[str], min_points: int) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for code in sorted(metric_codes):
        metric = METRICS.get(code)
        if metric is None or metric.value_type == "categorical":
            continue
        full = ctx.daily(code, days=BASELINE_WINDOW_DAYS + RECENT_EXCLUDE_DAYS + 1, include_current=False)
        cutoff = ctx.today - timedelta(days=RECENT_EXCLUDE_DAYS)
        series = {d: v for d, v in full.items() if d < cutoff}
        values = list(series.values())
        current = ctx.current_value(code)
        if metric.aggregate == "sum" and current is not None:
            today_total = ctx.daily(code, days=1, include_current=True).get(ctx.today)
            current = today_total if today_total is not None else current
        entry: dict = {
            "metric_code": code,
            "label": metric.label,
            "unit": metric.normalized_unit,
            "window_days": BASELINE_WINDOW_DAYS,
            "n_days": len(values),
            "current": current,
        }
        if len(values) < min_points:
            entry.update(available=False, reason=f"Only {len(values)} day(s) of valid reference history "
                                                 f"(excluding the last {RECENT_EXCLUDE_DAYS} days); {min_points} required.")
        else:
            summary = robust_summary(values, code)
            z = robust_z(current, summary["median"], summary["robust_spread"]) if current is not None else None
            entry.update(
                available=True,
                **summary,
                ewma=ewma(values),
                slope_per_day_14d=slope_per_day([(d, v) for d, v in full.items() if d != ctx.today][-14:]),
                reference_window=f"{min(series).isoformat()} to {max(series).isoformat()} (last {RECENT_EXCLUDE_DAYS} days excluded)",
                confidence=confidence_label(len(values)),
                robust_z=round(z, 2) if z is not None else None,
                pct_change=round((current - summary["median"]) / summary["median"] * 100, 1)
                if current is not None and summary["median"] else None,
                method=f"median ± 1.4826·MAD over daily values, excluding the most recent {RECENT_EXCLUDE_DAYS} days (robust z-score)",
            )
        out[code] = entry
    return out


class BaselineIQAgent(BaseAgent):
    agent_id = "baseline_iq"
    name = "BaselineIQ"
    scope = "Personal baseline: median, MAD, mean, SD, EWMA, range, trend slope and baseline confidence"
    method = "Robust statistics over up to 30 days of valid daily values (NumPy)"
    must_not = "Establish a baseline from too few measurements or treat deviation as a diagnosis"

    def analyze(self, ctx: AgentContext):
        min_points = int(ctx.settings.get("min_baseline_points", 7))
        metrics = {o["metric_code"] for o in ctx.valid_checkin_observations}
        baselines = compute_baselines(ctx, metrics, min_points)
        findings = []
        unavailable = [b for b in baselines.values() if not b["available"]]
        if unavailable:
            findings.append(Finding(
                code="BASELINE_UNAVAILABLE",
                summary="Personal baseline comparison unavailable for: "
                        + ", ".join(f"{b['label']} ({b['n_days']} day(s) of history)" for b in unavailable)
                        + ". These values are described but not compared and are not shown as normal.",
                statement_type="limitation",
                metric_codes=[b["metric_code"] for b in unavailable],
                limitations=[b["reason"] for b in unavailable],
            ))
        status = "completed" if any(b["available"] for b in baselines.values()) else "insufficient_data"
        ids = [o["observation_id"] for o in ctx.valid_checkin_observations]
        return self.result(ctx, status, findings, ids, output={"baselines": baselines},
                           activation_reason="Numeric measurements submitted that need personal comparison")
