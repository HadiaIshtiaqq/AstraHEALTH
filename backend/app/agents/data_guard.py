"""DataGuard — data-quality gate before any medical analysis agent sees the data."""
from __future__ import annotations

from datetime import timedelta

from app.agents.base import AgentContext, BaseAgent
from app.db.database import parse_iso
from app.domain.metrics import CHECKIN_CORE_METRICS, METRICS
from app.schemas.models import Finding
from app.services.validation import QUALITY_MESSAGES


class DataGuardAgent(BaseAgent):
    agent_id = "data_guard"
    name = "DataGuard"
    scope = "Data quality: schema, units, timestamps, plausibility, duplicates, missing core measurements"
    method = "Deterministic validation against the metric registry; quality flags assigned at ingestion"
    must_not = "Silently discard unusual values or convert values from unknown units"

    def analyze(self, ctx: AgentContext):
        findings: list[Finding] = []
        by_status: dict[str, list[dict]] = {}
        for obs in ctx.checkin_observations:
            by_status.setdefault(obs["quality_status"], []).append(obs)

        for status in ("implausible", "duplicate", "stale", "pending_confirmation", "invalid"):
            items = by_status.get(status, [])
            if not items:
                continue
            labels = ", ".join(sorted({METRICS[o['metric_code']].label for o in items if o["metric_code"] in METRICS}))
            flag = "unconfirmed" if status == "pending_confirmation" else status
            findings.append(Finding(
                code="DATA_QUALITY_FLAG",
                summary=f"{len(items)} observation(s) flagged as {status.replace('_', ' ')}: {labels}. "
                        f"{QUALITY_MESSAGES.get(flag, '')}",
                statement_type="observation",
                metric_codes=sorted({o["metric_code"] for o in items}),
                evidence_observation_ids=[o["observation_id"] for o in items],
                data={"quality_status": status, "count": len(items)},
            ))

        context_missing = [o for o in ctx.checkin_observations if "context_missing" in o.get("quality_flags", [])]
        if context_missing:
            findings.append(Finding(
                code="MEASUREMENT_CONTEXT_MISSING",
                summary="Heart rate was recorded without measurement context (resting or post-exercise), "
                        "which limits comparison with the resting baseline.",
                statement_type="limitation",
                metric_codes=["heart_rate"],
                evidence_observation_ids=[o["observation_id"] for o in context_missing],
            ))

        # Missing core measurements for today (distinguishes 'not measured' from invalid).
        day_start = ctx.reference_time - timedelta(hours=24)
        recent_metrics = {
            o["metric_code"] for o in ctx.history
            if parse_iso(o["measured_at"]) >= day_start
        } | ctx.checkin_metrics()
        missing = [m for m in CHECKIN_CORE_METRICS if m not in recent_metrics]
        if missing:
            findings.append(Finding(
                code="MISSING_CORE_MEASUREMENTS",
                summary="Not measured in the last 24 hours: " + ", ".join(METRICS[m].label for m in missing) + ".",
                statement_type="limitation",
                metric_codes=missing,
                data={"missing": missing},
            ))

        valid = ctx.valid_checkin_observations
        status = "completed" if valid else "insufficient_data"
        return self.result(
            ctx, status, findings,
            input_ids=[o["observation_id"] for o in ctx.checkin_observations],
            output={
                "counts": {k: len(v) for k, v in by_status.items()},
                "valid_observation_ids": [o["observation_id"] for o in valid],
                "excluded_observation_ids": [o["observation_id"] for o in ctx.checkin_observations if o["quality_status"] != "valid"],
                "missing_core_metrics": missing,
            },
            activation_reason="Runs on every submission before any analysis agent",
        )
