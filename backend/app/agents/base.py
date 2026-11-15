"""Agent contract: every specialist exposes analyze(context) -> AgentResult."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, ClassVar

from app.db.database import iso, parse_iso, utcnow
from app.domain.metrics import METRICS
from app.ml.stats import daily_series, zone
from app.schemas.models import AgentResult, Finding, MetricAssessment


@dataclass(frozen=True)
class AgentContext:
    """Immutable snapshot handed to each agent. Agents never write shared state."""

    run_id: str
    profile: dict
    reference_time: datetime
    checkin_id: str | None
    checkin_observations: tuple[dict, ...]  # every observation in the check-in, with quality status
    history: tuple[dict, ...]  # valid observations for the profile up to and including the check-in
    baselines: dict[str, dict] = field(default_factory=dict)  # BaselineIQ output, keyed by metric
    settings: dict[str, Any] = field(default_factory=dict)

    # ---- helpers -------------------------------------------------------
    @property
    def valid_checkin_observations(self) -> list[dict]:
        return [o for o in self.checkin_observations if o["quality_status"] == "valid"]

    def checkin_metrics(self) -> set[str]:
        return {o["metric_code"] for o in self.valid_checkin_observations}

    def current(self, metric_code: str) -> list[dict]:
        return [o for o in self.valid_checkin_observations if o["metric_code"] == metric_code]

    def current_value(self, metric_code: str) -> float | None:
        obs = self.current(metric_code)
        if not obs:
            return None
        values = [float(o["normalized_value"]) for o in obs if o["normalized_value"] is not None]
        if not values:
            return None
        if METRICS[metric_code].aggregate == "sum":
            return sum(values)
        return values[-1]

    def symptoms(self) -> set[str]:
        return {o["value_text"] for o in self.valid_checkin_observations if o["metric_code"] == "symptom"}

    def checkin_ids(self) -> set[str]:
        return {o["observation_id"] for o in self.checkin_observations}

    def prior_history(self, metric_code: str, days: int = 30) -> list[dict]:
        """Valid observations of a metric before the check-in (excludes the check-in itself)."""
        start = self.reference_time - timedelta(days=days)
        current_ids = self.checkin_ids()
        return [
            o for o in self.history
            if o["metric_code"] == metric_code
            and o["observation_id"] not in current_ids
            and start <= parse_iso(o["measured_at"]) <= self.reference_time
        ]

    def daily(self, metric_code: str, days: int = 30, include_current: bool = True) -> dict[date, float]:
        start = self.reference_time - timedelta(days=days)
        current_ids = self.checkin_ids()
        obs = [
            o for o in self.history
            if o["metric_code"] == metric_code
            and parse_iso(o["measured_at"]) >= start
            and parse_iso(o["measured_at"]) <= self.reference_time + timedelta(minutes=10)
            and (include_current or o["observation_id"] not in current_ids)
        ]
        return daily_series(obs, metric_code, self.tz)

    @property
    def tz(self) -> str:
        return self.profile.get("timezone") or "UTC"

    @property
    def today(self) -> date:
        """The crew member's local calendar day at the reference time."""
        return self.reference_time.astimezone(zone(self.tz)).date()


class BaseAgent:
    agent_id: ClassVar[str] = "base"
    name: ClassVar[str] = "Base"
    version: ClassVar[str] = "1.0.0"
    scope: ClassVar[str] = ""
    metrics: ClassVar[tuple[str, ...]] = ()
    method: ClassVar[str] = ""
    must_not: ClassVar[str] = ""

    def analyze(self, ctx: AgentContext) -> AgentResult:  # pragma: no cover - interface
        raise NotImplementedError

    # ---- result helpers --------------------------------------------------
    def result(
        self,
        ctx: AgentContext,
        status: str,
        findings: list[Finding] | None = None,
        input_ids: list[str] | None = None,
        assessments: list[MetricAssessment] | None = None,
        limitations: list[str] | None = None,
        activation_reason: str = "",
        output: dict | None = None,
    ) -> AgentResult:
        findings = findings or []
        for f in findings:
            f.agent_id = self.agent_id
        return AgentResult(
            run_id=ctx.run_id,
            agent_id=self.agent_id,
            agent_name=self.name,
            agent_version=self.version,
            status=status,  # type: ignore[arg-type]
            input_observation_ids=input_ids or [],
            findings=findings,
            assessments=assessments or [],
            limitations=limitations or [],
            activation_reason=activation_reason,
            method=self.method,
            output=output or {},
            created_at=iso(utcnow()),
        )

    def describe(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "version": self.version,
            "scope": self.scope,
            "metrics": list(self.metrics),
            "method": self.method,
            "must_not": self.must_not,
        }


def fmt(value: float | None, metric_code: str) -> str:
    if value is None:
        return "—"
    metric = METRICS[metric_code]
    unit = metric.normalized_unit
    if metric.value_type == "scale":
        return f"{value:g}/5"
    if metric.value_type == "boolean":
        return "yes" if value >= 1 else "no"
    digits = 1 if metric_code in ("body_temperature", "sleep_duration", "body_mass") else 0
    if metric_code == "radiation_dose":
        digits = 3
    return f"{value:.{digits}f} {unit}"


def direction_word(z: float, metric_code: str) -> str:
    return "above" if z > 0 else "below"


def baseline_ids(ctx: AgentContext, metric_code: str) -> list[str]:
    return [o["observation_id"] for o in ctx.current(metric_code)]
